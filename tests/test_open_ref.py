# -*- coding: utf-8 -*-
"""ลิงก์ Ref No. บน ERP-KOLA: kola-netbay://open?ref=... -> login -> ค้นหา Reference No. -> เปิดใบขน (NETBAY จำลอง)"""
import dataclasses

import pytest

from conftest import serve
from core import netbay
from mock_netbay import create_mock
from open_ref import parse_ref


@pytest.fixture
def nb(settings, tmp_path):
    mock = create_mock()
    srv, url = serve(mock)
    s = dataclasses.replace(settings.netbay, url=url, username='u1', password='p1', headless=True)
    yield s, mock.state
    srv.shutdown()


def test_opens_the_declaration_found_by_reference_no(nb, tmp_path):
    s, state = nb
    lines = []
    got = netbay.open_declaration('QENX000000042', s, log=lines.append, profiles_dir=str(tmp_path), keep_open=False)
    assert got == '16300'
    assert state['login'] == ('u1', 'p1')
    assert state['searched'] == ['QENX000000042']
    assert 'เปิดใบขน QENX000000042 แล้ว' in lines
    assert state.get('created') is None              # เปิดดูอย่างเดียว ไม่สร้างใบขนใหม่


def test_unknown_reference_no_is_reported_on_screen(nb, tmp_path):
    s, state = nb
    lines = []
    assert netbay.open_declaration('QENX000000777', s, log=lines.append,
                                   profiles_dir=str(tmp_path), keep_open=False) is None
    assert 'ไม่พบใบขน QENX000000777' in lines


def test_reference_no_from_link():
    assert parse_ref('kola-netbay://open?ref=QENX000000020') == 'QENX000000020'
    assert parse_ref('kola-netbay://open/?ref=qenx000000020&x=1') == 'QENX000000020'
    assert parse_ref(' QELS100015902 ') == 'QELS100015902'
    for bad in ('', 'kola-netbay://open', 'QENX\'; alert(1)//', 'A' * 60):
        with pytest.raises(SystemExit):
            parse_ref(bad)
