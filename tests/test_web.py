# -*- coding: utf-8 -*-
"""ทดสอบผ่านหน้าเว็บจริงด้วย Playwright: อัปโหลด -> สร้าง CSV -> ดาวน์โหลด -> ส่งเข้า NETBAY (จำลอง)"""
import dataclasses
import datetime

import pytest
from openpyxl import Workbook
from playwright.sync_api import expect, sync_playwright

from app import create_app
from conftest import make_msfz, serve
from mock_netbay import IMPORTER, create_mock


@pytest.fixture
def site(settings):
    mock = create_mock()
    mock_srv, mock_url = serve(mock)
    nb = dataclasses.replace(settings.netbay, url=mock_url, username='u1', password='p1', headless=True)
    s = dataclasses.replace(settings, netbay=nb)
    app_srv, app_url = serve(create_app(s))
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel='chrome')   # Google Chrome ในเครื่อง (ตัวเดียวกับที่โปรแกรมใช้)
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page(accept_downloads=True)
        page.goto(app_url)
        yield page, mock.state
        browser.close()
    app_srv.shutdown()
    mock_srv.shutdown()


def test_upload_create_csv_and_send_to_netbay(site, tmp_path):
    page, netbay = site
    expect(page.locator('#chips')).to_contain_text('ฐานข้อมูลเลขเครื่อง 0 เลข')

    page.locator('#file').set_input_files(make_msfz(str(tmp_path / 'ใบแจ้งหนี้.xlsx')))
    rows = page.locator('#cars tbody tr')
    expect(rows).to_have_count(3)
    expect(page.locator('#commitBtn')).to_be_enabled()
    expect(rows.nth(0).locator('td.engine').nth(1)).to_have_text('HR15-xxxxxxx')

    page.locator('#commitBtn').click()
    expect(page.locator('#messages')).to_contain_text('สร้าง CSV สำเร็จ')
    engine = rows.nth(0).locator('td.engine').nth(1).inner_text()
    assert engine.startswith('HR15-') and len(engine) == len('HR15-1234567')
    expect(page.locator('#runs tbody tr')).to_have_count(1)

    with page.expect_download() as dl:
        page.locator('#dlCsv').click()
    assert dl.value.suggested_filename == 'TESTBL0001.csv'
    with open(dl.value.path(), 'rb') as f:
        csv_bytes = f.read()
    assert engine in csv_bytes.decode('tis-620')

    page.once('dialog', lambda d: d.accept())
    page.locator('#netbayBtn').click()
    expect(page.locator('#netbayLog')).to_contain_text('เสร็จแล้ว', timeout=90_000)
    assert 'ผิดพลาด' not in page.locator('#netbayLog').inner_text()

    assert netbay['login'] == ('u1', 'p1')
    d = netbay['decl']
    assert (d['decl_type'], d['s5a'], d['s5b']) == ('610', '1', '9')
    assert d['importer_name'] == IMPORTER
    assert (d['vessel'], d['voyage'], d['bl'], d['origin1'], d['release_port']) == \
        ('OOCL BANGKOK', 'XXXX', 'TESTBL0001', 'JP', '2836')
    assert (d['pkg_amount'], d['pkg_unit'], d['gw1'], d['gw2'], d['price'], d['currency']) == \
        ('3', 'UN', '4330', '4330', '1022700.5', 'JPY')
    assert d['arrival'] == datetime.date.today().strftime('%d-%m-%Y')
    assert netbay['upload'][1] == csv_bytes
    assert netbay['refresh'] == 1
    assert netbay['popups'] == [('gw', 'true'), ('duty', 'true'), ('vat', 'true')]
    assert netbay['recalc'] == ['avg', 'tax', 'cif']


def test_bad_file_cannot_be_committed(site, tmp_path):
    page, _ = site
    p = str(tmp_path / 'blank.xlsx')
    Workbook().save(p)
    page.locator('#file').set_input_files(p)
    expect(page.locator('#messages')).to_contain_text('ไม่รู้จักชนิดไฟล์')
    expect(page.locator('#commitBtn')).to_be_disabled()
