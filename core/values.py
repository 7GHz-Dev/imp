# -*- coding: utf-8 -*-
"""แปลงค่าจากเซลล์ Excel ให้เป็นข้อความ/ตัวเลขที่ใช้ต่อได้"""
import datetime
import re
from decimal import Decimal, InvalidOperation

EXCEL_ERRORS = {'#N/A', '#VALUE!', '#REF!', '#DIV/0!', '#NUM!', '#NAME?',
                '#NULL!', '#SPILL!', '#CALC!', '#GETTING_DATA'}


def clean(v):
    """ค่าในเซลล์ -> ข้อความที่ตัดช่องว่างซ้ำแล้ว  ว่างหรือ error ของ Excel -> ''"""
    if v is None:
        return ''
    if isinstance(v, str):
        s = ' '.join(v.split())
        return '' if s.upper() in EXCEL_ERRORS else s
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, datetime.datetime):
        return v.strftime('%d/%m/%Y')
    return str(v)


def to_decimal(v):
    """ค่าในเซลล์ -> Decimal  อ่านไม่ได้ -> None"""
    s = clean(v).replace(',', '')
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def fmt_number(d):
    """Decimal -> ข้อความ  1370 ไม่ใช่ 1370.0  ส่วน 172700.1 คงทศนิยมไว้"""
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), 'f')


def fmt_date(v):
    """วันที่ invoice -> dd/mm/yyyy  (รับได้ทั้งเซลล์วันที่และข้อความ 7/8/2026)"""
    if isinstance(v, datetime.datetime):
        return v.strftime('%d/%m/%Y')
    s = clean(v)
    m = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m:
        return '%02d/%02d/%s' % (int(m.group(1)), int(m.group(2)), m.group(3))
    return s
