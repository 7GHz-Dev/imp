# -*- coding: utf-8 -*-
"""
ERP-KOLA จำลองสำหรับทดสอบ worker.py

ทำเฉพาะ POST /api/worker ตามสัญญาเดียวกับ v2/src/app/api/worker/route.ts ของ ERP-KOLA
(key + fn + args  ตอบ {ok, data} หรือ {ok: false, error})  แล้วเก็บสิ่งที่ worker ส่งมาไว้ใน state
"""
import base64
import os

from flask import Flask, jsonify, request

KEY = 'test-worker-key'


def create_mock_erp():
    app = Flask(__name__)
    state = {'tasks': [], 'completed': [], 'failed': [], 'heartbeats': [], 'fail_complete': 0}
    app.state = state

    def add_task(path, task_id=None, job_id='JOB-0001', job_no='MU2026100001', bl_no='TESTBL0001'):
        with open(path, 'rb') as f:
            body = f.read()
        task = {'id': task_id or 'TASK-%04d' % (len(state['tasks']) + 1), 'jobId': job_id, 'status': 'QUEUED',
                'data': {'jobNo': job_no, 'blNo': bl_no}, 'fileName': os.path.basename(path), 'body': body}
        state['tasks'].append(task)
        return task
    app.add_task = add_task

    ok = lambda data: jsonify(ok=True, data=data)

    @app.post('/api/worker')
    def worker():
        body = request.get_json()
        if body.get('key') != KEY:
            return jsonify(ok=False, error='UNAUTHORIZED|API key ไม่ถูกต้อง'), 401
        fn, args = body.get('fn'), body.get('args') or {}
        task = next((t for t in state['tasks'] if t['id'] == args.get('taskId')), None)

        if fn == 'claimNext':
            if args.get('type') != 'DRAFT_ENTRY':
                return jsonify(ok=False, error='worker ต้องขอเฉพาะงาน DRAFT_ENTRY'), 400
            for t in state['tasks']:
                if t['status'] == 'QUEUED':
                    t['status'], t['claimedBy'] = 'PROCESSING', args.get('worker')
                    return ok({'task': {'id': t['id'], 'type': 'DRAFT_ENTRY', 'jobId': t['jobId'], 'data': t['data'],
                                        'hasInputFile': True, 'inputFileName': t['fileName'], 'attempts': 1}})
            return ok({'task': None})
        if fn == 'downloadInputFile':
            return ok({'fileName': task['fileName'], 'mimeType': 'application/octet-stream',
                       'base64': base64.b64encode(task['body']).decode()})
        if fn == 'completeTask':
            if state['fail_complete']:
                state['fail_complete'] -= 1
                return jsonify(ok=False, error='เน็ตหลุด (จำลอง)'), 500
            if not (args.get('refNo') or '').strip():
                return jsonify(ok=False, error='งาน DRAFT_ENTRY ต้องส่ง refNo กลับมา'), 400
            f = args.get('file') or {}
            state['completed'].append({'taskId': task['id'], 'refNo': args['refNo'], 'url': args.get('url'),
                                       'fileName': f.get('name'),
                                       'file': base64.b64decode(f['base64']) if f.get('base64') else None})
            task['status'] = 'DONE'
            return ok({'ok': True})
        if fn == 'failTask':
            state['failed'].append({'taskId': task['id'], 'error': args.get('error')})
            task['status'] = 'ERROR'
            return ok({'ok': True})
        if fn == 'heartbeat':
            state['heartbeats'].append(args)
            return ok({'settings': {'background': False, 'stopAt': None}})
        return jsonify(ok=False, error='FORBIDDEN|ไม่อนุญาตคำสั่ง %s' % fn), 403

    return app
