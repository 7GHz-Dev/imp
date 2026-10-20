# -*- coding: utf-8 -*-
"""
worker สร้าง Draft ใบขนให้ ERP-KOLA  (PAINT > งานคงค้าง > 3. Draft ใบขน)

PAINT กด "สร้าง Draft" -> งาน DRAFT_ENTRY เข้าคิวบน ERP พร้อมไฟล์ Final Invoice
worker นี้รันบนเครื่องที่เปิด NETBAY (192.168.1.123) ได้ และเป็นฝ่ายถาม ERP เอง (ไม่ต้องเปิด port ให้ใครเข้ามา)
  1. ตรวจ invoice แบบหน้าเว็บ imp  ไม่ผ่าน = ส่งเหตุผลกลับไปที่งาน ไม่สร้างอะไร
  2. สุ่มเลขเครื่อง (data/engine.db) เติมลง Excel และสร้าง CSV  ->  output/<วันเวลา>_<BL>/
     chassis ที่เคยได้เลขใน BL เดียวกันใช้เลขเดิม (กดสร้าง Draft ซ้ำได้ เลขไม่เปลี่ยน)
  3. สร้างใบขนใน NETBAY กรอกหัวใบขน แนบ CSV (Add Invoice -> Import)
     จบเมื่อ NETBAY ขึ้น "success please check your invoice"  (ไม่กด Save / Send to Customs)
  4. ส่ง Reference No. และ invoice ที่เติมเลขเครื่องแล้วกลับเข้างานใน ERP

    python worker.py          รอรับงานไปเรื่อย ๆ  (ปิด: Ctrl+C)
    python worker.py --once   ทำงานที่ค้างในคิว 1 งานแล้วจบ

ตั้งค่า: config.ini หัวข้อ [erp] (api_key = WORKER_API_KEY ของ ERP) และ [netbay]
"""
import base64
import collections
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request

from core import config, netbay, pipeline
from core.engine_db import EngineDB

TASK_TYPE = 'DRAFT_ENTRY'
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
MAX_UPLOAD = 3_000_000          # ความยาว base64 สูงสุดที่ส่งไฟล์ขึ้น ERP


class ErpError(Exception):
    pass


class DraftError(Exception):
    """invoice หรือข้อมูลงานมีปัญหาที่ PAINT ต้องแก้ — ข้อความนี้ไปแสดงที่งานใน ERP"""


class Erp:
    """REST ของ ERP-KOLA สำหรับ worker:  POST /api/worker  {key, fn, args}"""

    def __init__(self, url, key, timeout=120):
        self.url, self.key, self.timeout = url.rstrip('/') + '/api/worker', key, timeout

    def call(self, fn, **args):
        body = json.dumps({'key': self.key, 'fn': fn, 'args': args}).encode('utf-8')
        req = urllib.request.Request(self.url, data=body, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            try:
                data = json.load(e)
            except ValueError:
                raise ErpError('%s: HTTP %s' % (fn, e.code)) from None
        except (urllib.error.URLError, OSError) as e:
            raise ErpError('%s: ติดต่อ ERP ไม่ได้ (%s)' % (fn, getattr(e, 'reason', e))) from None
        if not data.get('ok'):
            raise ErpError('%s: %s' % (fn, data.get('error')))
        return data.get('data')


def _norm_bl(s):
    return re.sub(r'[^0-9A-Z]', '', (s or '').upper())


class Worker:
    retry_waits = (0, 5, 20, 60)        # วินาทีที่รอก่อนส่งผลกลับ ERP แต่ละครั้ง

    def __init__(self, settings, erp=None, db=None):
        self.s = settings
        self.erp = erp or Erp(settings.erp.url, settings.erp.api_key)
        self.db = db or EngineDB(settings.db_path)
        self.name = settings.erp.worker_name or 'imp@%s' % socket.gethostname()
        self.lines = collections.deque(maxlen=80)
        self.busy = None
        self.done_dir = os.path.join(settings.work_dir, 'erp', 'done')
        os.makedirs(self.done_dir, exist_ok=True)

    # ------------------------------------------------------------ สถานะ

    def log(self, msg):
        line = '%s  %s' % (time.strftime('%H:%M:%S'), msg)
        self.lines.append(line)
        print(line, flush=True)

    def heartbeat(self, shot=None, offline=False):
        """บอก ERP ว่ายังเปิดอยู่ ทำอะไรอยู่  mode=draft แยกจาก worker แลก DO"""
        args = dict(worker=self.name, busy=self.busy, mode='draft', platform=sys.platform,
                    headless=self.s.netbay.headless, log=list(self.lines), offline=offline)
        if shot:
            args['shot'] = shot
        try:
            self.erp.call('heartbeat', **args)
        except ErpError as e:
            print('heartbeat: %s' % e, flush=True)

    def snap(self, page):
        """ภาพหน้าจอ NETBAY ขึ้น ERP ระหว่างทำงาน"""
        try:
            shot = base64.b64encode(page.screenshot(type='jpeg', quality=45)).decode()
        except Exception:
            shot = None
        self.heartbeat(shot)

    # ------------------------------------------------------------ คิว

    def run(self, once=False):
        if not self.s.erp.api_key:
            raise SystemExit('ยังไม่ได้ใส่ api_key ใน config.ini หัวข้อ [erp] (WORKER_API_KEY ของ ERP)')
        self.log('worker %s รับงาน Draft ใบขนจาก %s' % (self.name, self.s.erp.url))
        try:
            while True:
                self.heartbeat()
                try:
                    task = self.erp.call('claimNext', type=TASK_TYPE, worker=self.name)['task']
                except ErpError as e:
                    self.log('ถามคิวไม่ได้: %s' % e)
                    task = None
                if task:
                    self.process(task)
                if once:
                    return
                if not task:
                    time.sleep(self.s.erp.poll_seconds)
        except KeyboardInterrupt:
            self.log('ปิด worker')
        finally:
            self.busy = None
            self.heartbeat(offline=True)

    def process(self, task):
        data = task.get('data') or {}
        self.busy = 'Draft ใบขน %s' % (data.get('jobNo') or data.get('blNo') or task['id'])
        self.log('รับงาน %s  (งาน %s  BL %s)' % (task['id'], data.get('jobNo') or '-', data.get('blNo') or '-'))
        self.heartbeat()
        info = {}
        try:
            done = self._done(task['id'])
            if done:     # ทำใน NETBAY ไปแล้วแต่ส่งผลกลับไม่ถึง — ส่งซ้ำ ไม่สร้างใบขนใบที่สอง
                self.log('งานนี้สร้างใบขน %s ไปแล้ว — ส่งผลกลับอีกครั้ง' % done['ref_no'])
                ref, excel = done['ref_no'], done['excel']
            else:
                ref, excel = self.make_draft(task, info)
                self._mark_done(task['id'], ref, excel)
        except DraftError as e:
            self.fail(task, str(e))
        except Exception as e:
            msg = '%s: %s' % (type(e).__name__, e)
            if info.get('ref_no'):
                msg += ' — ใบขน %s ถูกสร้างค้างไว้ใน NETBAY (ลบ หรือเปิดทำต่อเองได้)' % info['ref_no']
            self.fail(task, msg)
        else:
            self.complete(task, ref, excel)
        finally:
            self.busy = None
            self.heartbeat()

    def complete(self, task, ref, excel):
        with open(excel, 'rb') as f:
            body = base64.b64encode(f.read()).decode()
        file = {'name': os.path.basename(excel), 'mimeType': XLSX_MIME, 'base64': body}
        if len(body) > MAX_UPLOAD:      # Vercel รับ request ได้ราว 4.5MB — ส่ง Ref No. ให้ถึงก่อน
            self.log('ไฟล์ %s ใหญ่เกินส่งขึ้น ERP — ส่งเฉพาะ Ref No. (ไฟล์อยู่ที่ %s)' % (file['name'], excel))
            file = None
        for wait in self.retry_waits:
            time.sleep(wait)
            try:
                # ไม่ส่งลิงก์หน้าใบขน: URL ของ NETBAY พก UCODE ของ session นี้ (เปิดที่อื่นไม่ได้อยู่แล้ว)
                # ERP ทำ Ref No. เป็นลิงก์ kola-netbay:// ให้ imp ในเครื่องคนกด login แล้วค้นหาเปิดเอง
                self.erp.call('completeTask', taskId=task['id'], refNo=ref, file=file)
                self.log('เสร็จ: ใบขน %s ส่งกลับ ERP แล้ว' % ref)
                return
            except ErpError as e:
                self.log('ส่งผลกลับ ERP ไม่ได้: %s' % e)
        self.log('ยังส่งผลกลับไม่ได้ — งานจะถูกหยิบใหม่ใน 30 นาที แล้วส่ง %s ซ้ำ (ไม่สร้างใบขนใหม่)' % ref)

    def fail(self, task, message):
        self.log('ไม่สำเร็จ: %s' % message)
        try:
            self.erp.call('failTask', taskId=task['id'], error=message[:1000])
        except ErpError as e:
            self.log('ส่งเหตุผลกลับ ERP ไม่ได้: %s' % e)

    def _done(self, task_id):
        p = os.path.join(self.done_dir, re.sub(r'[^\w.-]', '_', task_id) + '.json')
        if os.path.isfile(p):
            with open(p, encoding='utf-8') as f:
                d = json.load(f)
            if os.path.isfile(d.get('excel', '')):
                return d
        return None

    def _mark_done(self, task_id, ref, excel):
        p = os.path.join(self.done_dir, re.sub(r'[^\w.-]', '_', task_id) + '.json')
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'ref_no': ref, 'excel': excel, 'at': time.strftime('%Y-%m-%d %H:%M:%S')},
                      f, ensure_ascii=False)

    # ------------------------------------------------------------ งาน 1 ชิ้น

    def make_draft(self, task, info):
        data = task.get('data') or {}
        if not task.get('hasInputFile'):
            raise DraftError('งานนี้ไม่มีไฟล์ Final Invoice')
        f = self.erp.call('downloadInputFile', taskId=task['id'])
        name = f.get('fileName') or task.get('inputFileName') or 'invoice.xlsx'
        ext = os.path.splitext(name)[1].lower()
        if ext not in ('.xlsx', '.xlsm'):
            raise DraftError('Final Invoice ต้องเป็นไฟล์ Excel (.xlsx) — ไฟล์ที่แนบคือ %s' % name)
        d = os.path.join(self.s.work_dir, 'erp', re.sub(r'[^\w.-]', '_', task['id']))
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, 'invoice' + ext)
        with open(path, 'wb') as fh:
            fh.write(base64.b64decode(f['base64']))
        self.log('ได้ไฟล์ %s' % name)

        a = pipeline.analyze(path, self.s, self.db, reuse_bl=True)
        if not a.ok:
            raise DraftError('invoice ไม่ผ่านการตรวจ:\n- ' + '\n- '.join(a.errors or ['ไม่พบรถในไฟล์']))
        bl = a.invoice.bl_no
        want = data.get('blNo') or ''
        if want and _norm_bl(bl) not in _norm_bl(want) and _norm_bl(want) not in _norm_bl(bl):
            raise DraftError('เลข BL ใน invoice (%s) ไม่ตรงกับงาน (%s) — ตรวจว่าแนบ Final Invoice ถูกงาน' % (bl, want))
        for w in a.warnings:
            self.log('  เตือน: %s' % w)
        missing = sum('X' in line.tariff for line in a.lines)
        if missing:      # เหมือนโปรแกรมเดิม: ไม่พบพิกัด = XXXX  หลายพิกัด = 0000XXXX  ไปแก้ในใบขนเอง
            self.log('  พิกัดยังไม่ครบ %d คัน — ใส่ XXXX ไว้ ต้องแก้ในใบขนบน NETBAY' % missing)

        run = pipeline.commit(path, self.s, self.db, original_name=name, reuse_bl=True)
        counts = collections.Counter(c['status'] for c in run['cars'])
        self.log('เลขเครื่อง %d คัน (สุ่มใหม่ %d · ใช้เลขเดิม %d)  CSV %s'
                 % (len(run['cars']), counts[pipeline.NEW],
                    len(run['cars']) - counts[pipeline.NEW], run['csv']))
        self.heartbeat()

        run_dir = os.path.join(self.s.output_dir, run['run_id'])
        ref = netbay.upload(os.path.join(run_dir, run['csv']), run['bl_no'], run['totals'], self.s.netbay,
                            log=self.log, wait_close=False, until='import', on_step=self.snap, info=info)
        return ref, os.path.join(run_dir, run['excel'])


def main():
    Worker(config.load()).run(once='--once' in sys.argv)


if __name__ == '__main__':
    main()
