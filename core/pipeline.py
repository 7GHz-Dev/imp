# -*- coding: utf-8 -*-
"""
ขั้นตอนหลัก

analyze(path)  ตรวจไฟล์ + เตรียมข้อมูล  ไม่เขียนอะไรเลย (ใช้แสดงตัวอย่างก่อนยืนยัน)
commit(path)   สุ่มเลขเครื่อง -> เขียน Excel -> เขียน CSV  ทั้งหมดใน transaction เดียว
               ถ้าขั้นไหนล้ม เลขที่สุ่มจะไม่ถูกบันทึกและไม่มีไฟล์ค้าง
"""
import datetime
import json
import os
import re
import shutil
from dataclasses import dataclass, field

from . import netbay_csv as NC
from . import tariff as T
from .excel_out import write_engines
from .invoice import Car, EngineCell, Invoice, read_invoice
from .values import clean, fmt_number

NEW, REUSE, KEEP, AGAIN = 'new', 'reuse', 'keep', 'again'
STATUS_TEXT = {
    NEW: 'สุ่มใหม่',
    REUSE: 'ใช้เลขเดิม',      # เลขในไฟล์เคยออกให้ chassis นี้แล้ว
    KEEP: 'มีเลขแล้ว',        # เลขครบในไฟล์แต่ไม่อยู่ในฐานข้อมูล -> ใช้ตามไฟล์และบันทึกเพิ่ม
    AGAIN: 'ใช้เลขเดิมของ BL นี้',  # reuse_bl: ไฟล์ยังไม่มีเลข แต่ chassis เคยได้เลขใน BL เดียวกัน -> เติมเลขเดิม
}
FILL = (NEW, AGAIN)            # สถานะที่ต้องเติมเลขลงช่องเลขเครื่องและ use_desc_good2


@dataclass
class Line:
    car: Car
    engine: EngineCell
    tariff: str
    status: str
    number: str = ''           # เลข 7 หลัก (ว่าง = ยังไม่สุ่ม)
    full_engine: str = ''      # เลขเครื่องเต็ม เช่น HR15-1234567

    def preview_engine(self):
        return self.full_engine or '%s-xxxxxxx' % self.engine.head

    def desc2_full(self):
        return NC.add_number(self.car.desc2, self.number) if self.status in FILL else self.car.desc2


@dataclass
class Analysis:
    invoice: Invoice
    lines: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors and bool(self.lines)


class AnalysisError(Exception):
    def __init__(self, analysis):
        super().__init__('\n'.join(analysis.errors))
        self.analysis = analysis


def _norm(s):
    return re.sub(r'\s', '', s).upper()


_tariff_cache = {}


def _tariff_rows(inv, settings):
    if inv.tariff_sheet is not None:
        return T.load_rows(inv.tariff_sheet)
    path = settings.tariff_file
    key = (path, os.path.getmtime(path))
    if key not in _tariff_cache:
        _tariff_cache[key] = T.load_file(path)
    return _tariff_cache[key]


def analyze(path, settings, db, reuse_bl=False):
    """reuse_bl=True (worker ของ ERP): chassis ที่เคยได้เลขใน BL เดียวกัน ใช้เลขเดิม ไม่สุ่มใหม่
    — PAINT สร้าง Draft ซ้ำจาก Final Invoice ฉบับเดิมหรือฉบับแก้ เลขเครื่องจึงไม่เปลี่ยนไปเรื่อย ๆ"""
    inv = read_invoice(path)
    a = Analysis(invoice=inv, errors=list(inv.errors), warnings=list(inv.warnings))
    if not inv.cars or not inv.engines:
        if not a.errors:
            a.errors.append('ไม่พบช่องเลขเครื่องในส่วน invoice ของ template %s' % inv.file_type)
        return a

    if inv.tariff_sheet is None:
        a.warnings.append('ไฟล์ไม่มีชีต datatariff — ใช้ตารางพิกัดจาก %s' % os.path.basename(settings.tariff_file))
    tariff_rows = _tariff_rows(inv, settings)

    if len(inv.cars) != len(inv.engines):
        a.errors.append('ตารางสรุป (แถว 20 ลงไป) มี %d คัน แต่ invoice มีเลขเครื่อง %d คัน — '
                        'ตรวจว่าสูตรในตารางสรุปลากครบทุกคัน' % (len(inv.cars), len(inv.engines)))
        return a

    this_year = datetime.date.today().year
    seen_chassis, seen_numbers = {}, {}
    for car, eng in zip(inv.cars, inv.engines):
        tag = 'คันที่ %d (%s)' % (car.car_no, car.chassis)
        if _norm(car.chassis) != _norm(eng.chassis) or _norm(car.use_chassis) != _norm(eng.chassis):
            a.errors.append('%s: chassis ในตารางสรุปไม่ตรงกับ invoice แถว %d (%s)' % (tag, eng.row, eng.chassis))
            continue
        if car.chassis.encode('ascii', 'ignore').decode() != car.chassis:
            a.errors.append('%s: เลข chassis มีตัวอักษรแปลก %r' % (tag, car.chassis))
        if '(' not in car.desc2:
            a.errors.append('%s: use_desc_good2 ไม่มีวงเล็บ (%s)' % (tag, car.desc2))
            continue
        if _norm(car.desc2.split('(')[0]) != _norm(eng.head):
            a.errors.append('%s: use_desc_good2 "%s" ไม่ตรงกับเลขเครื่อง "%s" — เปิดไฟล์ใน Excel กด Save แล้วอัปโหลดใหม่'
                            % (tag, car.desc2, eng.head))
            continue
        if not 1980 <= int(car.year) <= this_year:
            a.warnings.append('%s: ปีผลิต %s ผิดปกติ' % (tag, car.year))
        if car.cc <= 0 or car.cc >= 11000 or (1980 <= car.cc <= this_year and car.cc % 10):
            a.warnings.append('%s: CC %d ผิดปกติ (อาจกรอกปีผิดช่อง)' % (tag, car.cc))
        if car.chassis in seen_chassis:
            a.warnings.append('%s: chassis ซ้ำกับคันที่ %d ในไฟล์เดียวกัน' % (tag, seen_chassis[car.chassis]))
        seen_chassis[car.chassis] = car.car_no

        code, note = T.lookup(tariff_rows, car)
        if note:
            a.warnings.append('%s: %s' % (tag, note))

        line = Line(car=car, engine=eng, tariff=code, status=NEW)
        existing = eng.existing_number
        if existing:
            line.number, line.full_engine = existing[1], eng.head
            used = db.find(line.number)
            if any(r['CHASSIS'] == car.chassis for r in used):
                line.status = REUSE
            elif used:
                a.errors.append('%s: เลข %s ถูกใช้กับ chassis %s แล้ว' % (tag, eng.head, used[0]['CHASSIS']))
            else:
                line.status = KEEP
                a.warnings.append('%s: เลขเครื่อง %s มีเลขครบแล้วแต่ไม่อยู่ในฐานข้อมูล — ใช้ตามไฟล์และบันทึกเพิ่ม'
                                  % (tag, eng.head))
            if line.number in seen_numbers:
                a.errors.append('%s: เลข %s ซ้ำกับคันที่ %d' % (tag, line.number, seen_numbers[line.number]))
            seen_numbers[line.number] = car.car_no
        else:
            old = db.history(car.chassis)
            same = [r for r in old if reuse_bl and _norm(r['BL_NO'] or '') == _norm(inv.bl_no)
                    and (r['FULL_ENG'] or '') == '%s-%s' % (eng.head, r['RANDOM_ENG'])]
            if same:
                line.status = AGAIN
                line.number, line.full_engine = same[0]['RANDOM_ENG'], same[0]['FULL_ENG']
                if line.number in seen_numbers:
                    a.errors.append('%s: เลข %s ซ้ำกับคันที่ %d' % (tag, line.number, seen_numbers[line.number]))
                seen_numbers[line.number] = car.car_no
            elif old:
                a.warnings.append('%s: chassis นี้เคยได้เลข %s (%s) — รอบนี้จะสุ่มเลขใหม่ '
                                  'ถ้าต้องการเลขเดิมให้อัปโหลดไฟล์ Excel ที่ได้จากรอบก่อน'
                                  % (tag, old[0]['FULL_ENG'], (old[0]['DATE_RAN'] or '')[:10]))
        a.lines.append(line)

    if not a.errors:
        try:   # ลองสร้าง CSV ด้วยเลขสมมติ เพื่อหาปัญหา (เช่นตัวอักษรที่เข้ารหัสไม่ได้) ก่อนจองเลขจริง
            _csv_bytes(a, settings, placeholder=True)
        except ValueError as e:
            a.errors.append('สร้าง CSV ไม่ได้: %s' % e)
    return a


def _csv_bytes(a, settings, placeholder=False):
    template = NC.CsvTemplate(settings.csv_template)
    brand_country = NC.load_brand_country(settings.brand_country)
    mapped = []
    for line in a.lines:
        if placeholder and line.status == NEW:
            desc2 = NC.add_number(line.car.desc2, '0000000')
        else:
            desc2 = line.desc2_full()
        mapped.append(NC.map_car(line.car, a.invoice, line.tariff, desc2, brand_country))
    rows = NC.build_rows(template, mapped)
    return NC.render(template, rows, settings.csv_encoding), NC.totals(template, rows)


def _safe(name):
    return re.sub(r'[^\w.-]+', '_', name).strip('_') or 'invoice'


def commit(path, settings, db, original_name='', reuse_bl=False):
    a = analyze(path, settings, db, reuse_bl=reuse_bl)
    if not a.ok:
        raise AnalysisError(a)
    inv = a.invoice
    base = _safe(inv.bl_no)
    stamp = datetime.datetime.now().strftime('%y%m%d-%H%M%S')
    run_id, n = '%s_%s' % (stamp, base), 1
    while os.path.exists(os.path.join(settings.output_dir, run_id)):
        n += 1
        run_id = '%s_%s_%d' % (stamp, base, n)
    run_dir = os.path.join(settings.output_dir, run_id)
    csv_path = os.path.join(run_dir, base + '.csv')
    excel_path = os.path.join(run_dir, base + '.xlsx')
    source = original_name or os.path.basename(path)

    os.makedirs(run_dir)
    try:
        with db.transaction() as tx:
            updates = []
            for line in a.lines:
                if line.status == NEW:
                    line.number, line.full_engine = tx.issue(
                        line.engine.head, line.car.chassis, inv.bl_no, inv.invoice_no, source)
                if line.status in FILL:
                    updates.append((line.engine.row, line.engine.col, line.engine.value_with(line.full_engine)))
                elif line.status == KEEP:
                    tx.add(line.number, line.full_engine, line.car.chassis, inv.bl_no, inv.invoice_no, source)

            method, after = write_engines(path, excel_path, updates,
                                          check_rows=[l.car.row for l in a.lines],
                                          method=settings.excel_method)
            for line in a.lines:
                if after and _norm(clean(after.get(line.car.row))) != _norm(line.desc2_full()):
                    a.warnings.append('คันที่ %d: Excel คำนวณ use_desc_good2 ได้ "%s" แต่ CSV ใช้ "%s"'
                                      % (line.car.car_no, clean(after.get(line.car.row)), line.desc2_full()))
            if method == 'openpyxl':
                a.warnings.append('ไม่ได้ใช้ Microsoft Excel เขียนไฟล์ — เปิดไฟล์ Excel ผลลัพธ์แล้วตรวจรูปแบบอีกครั้ง')

            data, totals = _csv_bytes(a, settings)
            with open(csv_path, 'wb') as f:
                f.write(data)

            run = {
                'run_id': run_id,
                'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'source_file': source,
                'file_type': inv.file_type,
                'invoice_no': inv.invoice_no,
                'invoice_date': inv.invoice_date,
                'bl_no': inv.bl_no,
                'csv': os.path.basename(csv_path),
                'excel': os.path.basename(excel_path),
                'excel_method': method,
                'totals': totals,
                'warnings': a.warnings,
                'cars': [line_dict(l) for l in a.lines],
            }
            with open(os.path.join(run_dir, 'run.json'), 'w', encoding='utf-8') as f:
                json.dump(run, f, ensure_ascii=False, indent=1)
    except BaseException:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    return run


def line_dict(l):
    return {
        'car_no': l.car.car_no,
        'brand': l.car.brand,
        'model': l.car.model,
        'chassis': l.car.chassis,
        'year': l.car.year,
        'cc': l.car.cc,
        'fuel': l.car.fuel,
        'weight': fmt_number(l.car.use_weight),
        'price': fmt_number(l.car.use_price),
        'tariff': l.tariff,
        'engine_before': l.engine.raw,
        'engine': l.preview_engine(),
        'status': l.status,
        'status_text': STATUS_TEXT[l.status],
    }


def analysis_dict(a):
    inv = a.invoice
    return {
        'ok': a.ok,
        'file_type': inv.file_type,
        'invoice_no': inv.invoice_no,
        'invoice_date': inv.invoice_date,
        'bl_no': inv.bl_no,
        'errors': a.errors,
        'warnings': a.warnings,
        'cars': [line_dict(l) for l in a.lines],
        'new_count': sum(l.status == NEW for l in a.lines),
    }


def list_runs(settings, limit=20):
    out = []
    if not os.path.isdir(settings.output_dir):
        return out
    for name in sorted(os.listdir(settings.output_dir), reverse=True):
        p = os.path.join(settings.output_dir, name, 'run.json')
        if os.path.isfile(p):
            with open(p, encoding='utf-8') as f:
                out.append(json.load(f))
            if len(out) >= limit:
                break
    return out


def load_run(settings, run_id):
    if not re.fullmatch(r'[\w.-]+', run_id or ''):
        return None
    p = os.path.join(settings.output_dir, run_id, 'run.json')
    if not os.path.isfile(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)
