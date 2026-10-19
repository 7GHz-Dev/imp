# -*- coding: utf-8 -*-
"""
ฐานข้อมูลเลขเครื่องที่ออกไปแล้ว (SQLite)

โครงสร้างเหมือนตาราง APP_RANDOM_ENG บน SQL Server เดิม
เพิ่ม BL_NO / INVOICE_NO / SOURCE_FILE ไว้ตามหาว่าเลขไหนออกให้ invoice ไหน

เลขสุ่ม = 7 หลัก (1000000-9999999) ต้องไม่ซ้ำกับ RANDOM_ENG ที่มีอยู่ทั้งตาราง
การจองทำใน transaction เดียว (BEGIN IMMEDIATE) — ถ้างานล้มกลางทาง เลขทั้งชุดจะไม่ถูกบันทึก
"""
import csv
import datetime
import os
import random
import sqlite3
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS APP_RANDOM_ENG (
    RANDOM_ENG  TEXT NOT NULL,
    FULL_ENG    TEXT,
    CHASSIS     TEXT NOT NULL,
    DATE_RAN    TEXT,
    BL_NO       TEXT,
    INVOICE_NO  TEXT,
    SOURCE_FILE TEXT,
    PRIMARY KEY (RANDOM_ENG, CHASSIS)
);
CREATE INDEX IF NOT EXISTS IX_APP_RANDOM_ENG_CHASSIS ON APP_RANDOM_ENG (CHASSIS);
"""

_rng = random.SystemRandom()


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class EngineDB:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with self._connect() as con:
            con.executescript(SCHEMA)

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        return con

    def count(self):
        con = self._connect()
        try:
            return con.execute('SELECT COUNT(*) FROM APP_RANDOM_ENG').fetchone()[0]
        finally:
            con.close()

    def find(self, number):
        """แถวทั้งหมดที่ใช้เลข 7 หลักนี้"""
        con = self._connect()
        try:
            return [dict(r) for r in con.execute(
                'SELECT * FROM APP_RANDOM_ENG WHERE RANDOM_ENG = ?', (number,))]
        finally:
            con.close()

    def history(self, chassis):
        """เลขที่เคยออกให้ chassis นี้ (ใหม่สุดก่อน)"""
        con = self._connect()
        try:
            return [dict(r) for r in con.execute(
                'SELECT * FROM APP_RANDOM_ENG WHERE CHASSIS = ? ORDER BY DATE_RAN DESC', (chassis,))]
        finally:
            con.close()

    @contextmanager
    def transaction(self):
        """ล็อกการเขียนไว้จนจบ block  ออกจาก block ปกติ = บันทึก, มี error = ยกเลิกทั้งหมด"""
        con = self._connect()
        con.execute('BEGIN IMMEDIATE')
        try:
            yield _Tx(con)
            con.execute('COMMIT')
        except BaseException:
            con.execute('ROLLBACK')
            raise
        finally:
            con.close()

    def import_csv(self, path):
        """นำเข้าข้อมูลเดิมจากไฟล์ export ของ SQL Server (RANDOM_ENG,FULL_ENG,CHASSIS,DATE_RAN)"""
        with open(path, encoding='utf-8-sig', newline='') as f:
            rows = [(r['RANDOM_ENG'].strip(), r['FULL_ENG'], r['CHASSIS'].strip(), r['DATE_RAN'] or None)
                    for r in csv.DictReader(f) if r['RANDOM_ENG'].strip() and r['CHASSIS'].strip()]
        con = self._connect()
        try:
            before = con.total_changes
            con.execute('BEGIN')
            con.executemany('INSERT OR IGNORE INTO APP_RANDOM_ENG '
                            '(RANDOM_ENG, FULL_ENG, CHASSIS, DATE_RAN, SOURCE_FILE) '
                            'VALUES (?, ?, ?, ?, \'import:' + os.path.basename(path) + '\')', rows)
            con.execute('COMMIT')
            return con.total_changes - before, len(rows)
        finally:
            con.close()


class _Tx:
    def __init__(self, con):
        self.con = con

    def is_used(self, number):
        return self.con.execute('SELECT 1 FROM APP_RANDOM_ENG WHERE RANDOM_ENG = ? LIMIT 1',
                                (number,)).fetchone() is not None

    def issue(self, head, chassis, bl_no='', invoice_no='', source_file=''):
        """สุ่มเลขใหม่ที่ไม่ซ้ำ แล้วบันทึก  คืน (เลข 7 หลัก, เลขเครื่องเต็ม)"""
        for _ in range(1000):
            number = str(_rng.randint(1000000, 9999999))
            if not self.is_used(number):
                break
        else:
            raise RuntimeError('สุ่มเลขไม่ซ้ำไม่ได้หลังลอง 1000 ครั้ง')
        full = '%s-%s' % (head, number)
        self.add(number, full, chassis, bl_no, invoice_no, source_file)
        return number, full

    def add(self, number, full, chassis, bl_no='', invoice_no='', source_file=''):
        self.con.execute(
            'INSERT INTO APP_RANDOM_ENG (RANDOM_ENG, FULL_ENG, CHASSIS, DATE_RAN, BL_NO, INVOICE_NO, SOURCE_FILE) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (number, full, chassis, _now(), bl_no, invoice_no, source_file))
