# -*- coding: utf-8 -*-
"""
นำเข้าเลขเครื่องเดิมจากไฟล์ export ของ SQL Server ลง SQLite

    python tools/import_db.py ../db_random_engine.csv

รันซ้ำได้ แถวที่มีอยู่แล้วจะถูกข้าม
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config  # noqa: E402
from core.engine_db import EngineDB  # noqa: E402


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    settings = config.load()
    db = EngineDB(settings.db_path)
    added, total = db.import_csv(sys.argv[1])
    print('อ่าน %d แถว  เพิ่มใหม่ %d แถว  ในฐานข้อมูลมีทั้งหมด %d แถว  (%s)'
          % (total, added, db.count(), settings.db_path))


if __name__ == '__main__':
    main()
