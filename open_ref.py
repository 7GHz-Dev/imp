# -*- coding: utf-8 -*-
"""
เปิดใบขนใน NETBAY จาก Reference No. — ลิงก์ Ref No. บน ERP-KOLA (kola-netbay://open?ref=...) เรียกตัวนี้

    python open_ref.py QENX000000020
    python open_ref.py "kola-netbay://open?ref=QENX000000020"

เปิด Chrome -> login -> Import -> ค้นหา Reference No. -> เปิดใบขนนั้น แล้วปล่อยหน้าต่างไว้ให้ตรวจต่อ
ติดตั้งให้ลิงก์บนเว็บเรียกได้: install/mac-netbay-launcher.sh  หรือ  install\\windows-netbay-launcher.cmd
log: work/open_ref.log
"""
import dataclasses
import os
import re
import sys
import time
import urllib.parse

from core import config, netbay

REF = re.compile(r'^[A-Z0-9][A-Z0-9-]{3,39}$')


def parse_ref(arg):
    """'QENX000000020' หรือ 'kola-netbay://open?ref=QENX000000020' -> 'QENX000000020'"""
    arg = (arg or '').strip()
    if '://' in arg:
        arg = (urllib.parse.parse_qs(urllib.parse.urlsplit(arg).query).get('ref') or [''])[0]
    ref = arg.strip().upper()
    if not REF.match(ref):
        raise SystemExit('Reference No. ไม่ถูกต้อง: %r' % arg)
    return ref


def main():
    s = config.load()
    os.makedirs(s.work_dir, exist_ok=True)
    log_path = os.path.join(s.work_dir, 'open_ref.log')

    def log(msg):
        line = '%s  %s' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg)
        print(line, flush=True)
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')

    ref = parse_ref(sys.argv[1] if len(sys.argv) > 1 else '')
    log('เปิดใบขน %s' % ref)
    try:
        netbay.open_declaration(ref, dataclasses.replace(s.netbay, headless=False), log=log,
                                profiles_dir=os.path.join(s.work_dir, 'netbay-browser'))
    except Exception as e:
        log('ไม่สำเร็จ: %s: %s' % (type(e).__name__, e))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
