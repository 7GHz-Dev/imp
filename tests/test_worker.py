# -*- coding: utf-8 -*-
"""worker.py กับ ERP-KOLA จำลอง + NETBAY จำลอง: รับงาน -> ตรวจ -> ออกเลข -> สร้างใบขน + Save -> ส่ง Ref No. กลับ"""
import dataclasses
import io

import pytest
from openpyxl import Workbook, load_workbook

from conftest import CARS, make_msfz, serve
from mock_erp import KEY, create_mock_erp
from mock_netbay import create_mock
from worker import Worker

WITH_TARIFF = CARS[:2]        # คันที่ 3 ในชุดทดสอบไม่มีพิกัด


@pytest.fixture
def env(settings, db):
    erp, nb = create_mock_erp(), create_mock()
    erp_srv, erp_url = serve(erp)
    nb_srv, nb_url = serve(nb)
    s = dataclasses.replace(
        settings,
        netbay=dataclasses.replace(settings.netbay, url=nb_url, username='u1', password='p1', headless=True),
        erp=dataclasses.replace(settings.erp, url=erp_url, api_key=KEY, worker_name='imp@test', poll_seconds=1),
    )
    w = Worker(s, db=db)
    w.retry_waits = (0, 0)
    yield w, erp, nb.state
    erp_srv.shutdown()
    nb_srv.shutdown()


def engines(xlsx_bytes):
    ws = load_workbook(io.BytesIO(xlsx_bytes)).worksheets[0]
    return [ws['J%d' % r].value for r in (20, 21)]


def test_creates_draft_saves_and_returns_ref_no(env, tmp_path, db):
    w, erp, netbay = env
    erp.add_task(make_msfz(str(tmp_path / 'FN.xlsx'), cars=WITH_TARIFF))
    w.run(once=True)

    assert erp.state['failed'] == []
    [done] = erp.state['completed']
    assert done['refNo'] == 'QENX000000099'
    assert done['url'].endswith('/decl?ImDclCtrl=16399'), 'ลิงก์หน้าใบขนต้องส่งกลับไปให้ ERP'
    assert done['fileName'] == 'TESTBL0001.xlsx'
    hr15, gr = engines(done['file'])
    assert hr15.startswith('HR15-') and gr.startswith('2GR-') and len(hr15) == len('HR15-1234567')

    assert netbay['saved'] == 1
    assert 'sent_to_customs' not in netbay
    assert netbay['decl']['bl'] == 'TESTBL0001' and netbay['refresh'] == 1
    assert hr15.encode() in netbay['upload'][1]
    assert db.count() == 2

    beats = erp.state['heartbeats']
    assert all(b['mode'] == 'draft' and b['worker'] == 'imp@test' for b in beats)
    assert any(b.get('shot') for b in beats)
    assert any(b['busy'] == 'Draft ใบขน MU2026100001' for b in beats)
    assert beats[-1]['offline'] is True
    assert any('QENX000000099' in line for line in beats[-1]['log'])


def test_draft_again_for_same_bl_keeps_engine_numbers(env, tmp_path, db):
    w, erp, netbay = env
    src = make_msfz(str(tmp_path / 'FN.xlsx'), cars=WITH_TARIFF)
    erp.add_task(src)
    w.run(once=True)
    erp.add_task(src, job_id='JOB-0001')          # FAH ตีกลับ -> PAINT กดสร้าง Draft ใหม่ด้วยไฟล์เดิม
    w.run(once=True)

    first, second = erp.state['completed']
    assert engines(first['file']) == engines(second['file'])
    assert db.count() == 2                          # ไม่ออกเลขเพิ่ม
    assert netbay['saved'] == 2


def test_result_is_resent_without_second_declaration(env, tmp_path):
    w, erp, netbay = env
    task = erp.add_task(make_msfz(str(tmp_path / 'FN.xlsx'), cars=WITH_TARIFF))
    erp.state['fail_complete'] = 2                   # ส่งผลกลับไม่ถึง ERP
    w.run(once=True)
    assert erp.state['completed'] == [] and netbay['saved'] == 1

    task['status'] = 'QUEUED'                        # ERP ปล่อยงานที่ค้างให้หยิบใหม่
    w.run(once=True)
    [done] = erp.state['completed']
    assert done['refNo'] == 'QENX000000099'
    assert done['url'].endswith('/decl?ImDclCtrl=16399'), 'ส่งซ้ำก็ต้องมีลิงก์เดิม'
    assert netbay['saved'] == 1                      # ไม่สร้างใบขนซ้ำ


def test_invoice_problems_go_back_to_paint(env, tmp_path, db):
    w, erp, netbay = env
    blank = str(tmp_path / 'blank.xlsx')
    Workbook().save(blank)
    erp.add_task(blank)
    erp.add_task(make_msfz(str(tmp_path / 'other.xlsx'), cars=WITH_TARIFF), bl_no='OTHERBL999')
    erp.add_task(make_msfz(str(tmp_path / 'notariff.xlsx')))
    pdf = tmp_path / 'FN.pdf'
    pdf.write_bytes(b'%PDF-1.4')
    erp.add_task(str(pdf))
    for _ in range(4):
        w.run(once=True)

    errors = [f['error'] for f in erp.state['failed']]
    assert 'ไม่รู้จักชนิดไฟล์' in errors[0]
    assert 'ไม่ตรงกับงาน (OTHERBL999)' in errors[1]
    assert 'ยังหาพิกัดไม่ได้' in errors[2] and 'MERCEDES BENZ C200' in errors[2]
    assert 'ต้องเป็นไฟล์ Excel' in errors[3]
    assert erp.state['completed'] == []
    assert netbay['login'] is None and db.count() == 0   # ไม่แตะ NETBAY ไม่ออกเลข


def test_netbay_failure_reports_the_half_made_declaration(env, tmp_path, monkeypatch):
    w, erp, _ = env
    import core.netbay as nb

    def broken(page, csv_path, log):
        raise nb.NetbayError('ไม่พบปุ่ม Import')
    monkeypatch.setattr(nb, 'attach_csv', broken)
    erp.add_task(make_msfz(str(tmp_path / 'FN.xlsx'), cars=WITH_TARIFF))
    w.run(once=True)
    [f] = erp.state['failed']
    assert 'ไม่พบปุ่ม Import' in f['error'] and 'QENX000000099' in f['error']
