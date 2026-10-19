# -*- coding: utf-8 -*-
"""
หน้าเว็บ: อัปโหลด invoice -> ตรวจ -> สุ่มเลขเครื่อง + สร้าง CSV -> ส่งเข้า NETBAY

    python app.py          แล้วเปิด http://127.0.0.1:5000
"""
import json
import os
import re
import shutil
import threading
import time
import uuid
import webbrowser

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from core import config, netbay, pipeline
from core.engine_db import EngineDB
from core.excel_out import excel_available

ALLOWED = ('.xlsx', '.xlsm')


class NetbayJob:
    def __init__(self, run, settings, csv_path):
        self.id = uuid.uuid4().hex[:12]
        self.run_id = run['run_id']
        self.status = 'running'
        self.log = []
        self._args = (csv_path, run['bl_no'], run['totals'], settings.netbay)
        self.thread = threading.Thread(target=self._work, daemon=True)

    def write(self, msg):
        self.log.append('%s  %s' % (time.strftime('%H:%M:%S'), msg))

    def _work(self):
        try:
            netbay.upload(*self._args, log=self.write)
            self.status = 'done'
        except Exception as e:
            self.write('ผิดพลาด: %s' % e)
            self.status = 'error'


def create_app(settings=None):
    settings = settings or config.load()
    db = EngineDB(settings.db_path)
    uploads = os.path.join(settings.work_dir, 'uploads')
    os.makedirs(uploads, exist_ok=True)
    _clean_old(uploads, days=7)

    app = Flask(__name__, template_folder='web')
    app.config['MAX_CONTENT_LENGTH'] = 30 * 1024 * 1024
    commit_lock = threading.Lock()
    jobs = {}

    def upload_dir(token):
        if not re.fullmatch(r'[0-9a-f]{32}', token or ''):
            abort(400)
        d = os.path.join(uploads, token)
        if not os.path.isdir(d):
            abort(404, 'ไม่พบไฟล์ที่อัปโหลด — อัปโหลดใหม่อีกครั้ง')
        return d

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/api/status')
    def status():
        nb = settings.netbay
        return jsonify(
            db_count=db.count(),
            excel=excel_available() and settings.excel_method != 'openpyxl',
            netbay_ready=bool(nb.url and nb.username and nb.password),
            netbay_url=nb.url,
            runs=pipeline.list_runs(settings),
        )

    @app.post('/api/analyze')
    def analyze():
        f = request.files.get('file')
        if not f or not f.filename:
            return jsonify(ok=False, errors=['ไม่ได้เลือกไฟล์']), 400
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED:
            return jsonify(ok=False, errors=['รองรับเฉพาะไฟล์ .xlsx (ไฟล์ .xls ให้เปิดใน Excel แล้ว Save As เป็น .xlsx)']), 400
        token = uuid.uuid4().hex
        d = os.path.join(uploads, token)
        os.makedirs(d)
        path = os.path.join(d, 'invoice' + ext)
        f.save(path)
        with open(os.path.join(d, 'meta.json'), 'w', encoding='utf-8') as m:
            json.dump({'filename': f.filename}, m, ensure_ascii=False)
        a = pipeline.analyze(path, settings, db)
        return jsonify(token=token, filename=f.filename, **pipeline.analysis_dict(a))

    @app.post('/api/commit')
    def commit():
        d = upload_dir((request.get_json(silent=True) or {}).get('token'))
        with open(os.path.join(d, 'meta.json'), encoding='utf-8') as m:
            name = json.load(m)['filename']
        path = next(os.path.join(d, n) for n in os.listdir(d) if n.startswith('invoice'))
        with commit_lock:
            try:
                run = pipeline.commit(path, settings, db, original_name=name)
            except pipeline.AnalysisError as e:
                return jsonify(**pipeline.analysis_dict(e.analysis)), 422
            except Exception as e:
                return jsonify(ok=False, errors=['%s: %s' % (type(e).__name__, e)], warnings=[]), 500
        return jsonify(ok=True, run=run)

    @app.get('/download/<run_id>/<kind>')
    def download(run_id, kind):
        run = pipeline.load_run(settings, run_id)
        if run is None or kind not in ('csv', 'excel'):
            abort(404)
        return send_from_directory(os.path.join(settings.output_dir, run_id), run[kind], as_attachment=True)

    @app.post('/api/netbay')
    def netbay_start():
        run = pipeline.load_run(settings, (request.get_json(silent=True) or {}).get('run_id'))
        if run is None:
            abort(404)
        if any(j.status == 'running' for j in jobs.values()):
            return jsonify(ok=False, error='กำลังส่งงานอื่นเข้า NETBAY อยู่ — รอให้เสร็จก่อน'), 409
        job = NetbayJob(run, settings, os.path.join(settings.output_dir, run['run_id'], run['csv']))
        jobs[job.id] = job
        job.thread.start()
        return jsonify(ok=True, job_id=job.id)

    @app.get('/api/netbay/<job_id>')
    def netbay_status(job_id):
        job = jobs.get(job_id) or abort(404)
        return jsonify(status=job.status, log=job.log, run_id=job.run_id)

    return app


def _clean_old(folder, days):
    limit = time.time() - days * 86400
    for name in os.listdir(folder):
        p = os.path.join(folder, name)
        if os.path.isdir(p) and os.path.getmtime(p) < limit:
            shutil.rmtree(p, ignore_errors=True)


if __name__ == '__main__':
    s = config.load()
    url = 'http://%s:%d' % (s.host, s.port)
    print('เปิดหน้าเว็บที่ %s  (ปิดโปรแกรม: Ctrl+C)' % url)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    create_app(s).run(host=s.host, port=s.port, threaded=True)
