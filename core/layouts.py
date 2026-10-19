# -*- coding: utf-8 -*-
"""
ตำแหน่งข้อมูลในไฟล์ invoice แต่ละ template

ทุก template มี "ตารางสรุป" อยู่ตำแหน่งเดียวกัน (สูตรใน template แปลงมาให้แล้ว)
  P4 ชนิดไฟล์   P5 วันที่ invoice   P6 เลข invoice   P14 เลข BL
  แถว 19 = หัวตาราง  แถว 20 ลงไป = รถ 1 คันต่อแถว  (คอลัมน์ P:U และ W:AF)
CSV จึงสร้างจากตารางสรุปได้ทุก template  ที่ต่างกันคือ "ช่องเลขเครื่อง" ที่ต้องเติมเลขสุ่ม
"""
from dataclasses import dataclass

TYPE_CELL = 'P4'
DATE_CELL = 'P5'
INVOICE_CELL = 'P6'
BL_CELL = 'P14'
FIRST_CAR_ROW = 20

# ตารางสรุป: ชื่อช่อง -> คอลัมน์
SUMMARY_COLS = {
    'desc1': 'P',        # use_desc_good1  เช่น "USED TOYOTA CROWN,"
    'desc2': 'Q',        # use_desc_good2  เช่น "4GR(GASOLINE/2490),2014"
    'use_chassis': 'R',  # use_chassis_no
    'use_weight': 'T',   # use_weight
    'use_price': 'U',    # use_price
    'car_no': 'W',
    'brand': 'X',
    'model': 'Y',
    'chassis': 'Z',
    'weight': 'AA',
    'year': 'AB',
    'cc': 'AC',
    'fuel': 'AD',
    'price': 'AE',
    'tariff': 'AF',
}


@dataclass(frozen=True)
class ColumnLayout:
    """รถ 1 คันต่อ 1 แถว เลขเครื่องอยู่คอลัมน์เดียวกันทุกแถว (MSFZ, JTC)"""
    header_row: int
    chassis_col: str
    engine_col: str


@dataclass(frozen=True)
class BlockLayout:
    """รถเป็นก้อน: หัวข้อคอลัมน์ C ค่าคอลัมน์ D เช่น CHASSIS NO. / ENGINE TYPE. (AICHI, HUAYO, JAN TRADING)"""
    first_row: int
    engine_label: str          # หัวข้อแถวเลขเครื่อง (ตัดช่องว่างและจุดแล้ว)
    chassis_label: str = 'CHASSISNO'
    label_col: str = 'C'
    value_col: str = 'D'


# ยกมาจาก set_engin_to_excel() ของโปรแกรมเดิม
LAYOUTS = {
    'MSFZ': ColumnLayout(header_row=19, chassis_col='E', engine_col='J'),
    'JTC': ColumnLayout(header_row=19, chassis_col='D', engine_col='K'),
    'AICHI': BlockLayout(first_row=17, engine_label='ENGINETYPE'),
    'HUAYO': BlockLayout(first_row=17, engine_label='ENGINETYPE'),
    'JAN TRADING': BlockLayout(first_row=16, engine_label='ENGINENO'),
}

ALIASES = {'JANTRADING': 'JAN TRADING'}


def normalize_type(text):
    t = ' '.join(str(text or '').upper().split())
    return ALIASES.get(t.replace(' ', ''), t)
