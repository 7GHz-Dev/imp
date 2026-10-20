# -*- coding: utf-8 -*-
"""
ส่ง CSV เข้า NETBAY ด้วย Playwright

ขั้นตอนและ XPath ยกมาจาก csv_to_netbay() ของโปรแกรมเดิม (Selenium):
  login -> หน้า import -> สร้างใบขนใหม่ (610) -> กรอกหัวใบขน -> แนบ CSV (Add Invoice -> Import)
  -> Refresh -> รวมน้ำหนัก/อากร/VAT จากทุก invoice -> คำนวณใหม่
upload(until='review')  หน้าเว็บ imp: ทำครบทุกขั้น แล้วหยุดให้คนตรวจและกด Save เอง
upload(until='import')  worker.py: จบทันทีที่ NETBAY ขึ้น "success please check your invoice" หลัง Import
open_declaration()      ลิงก์ Ref No. บน ERP-KOLA: login -> Import -> ค้นหา Reference No. -> เปิดใบขนนั้น
ไม่มีขั้นไหนกด Save หรือ Send to Customs ให้
"""
import datetime
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time

from playwright.sync_api import Error as PWError
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

D = 'xpath=//*[@id="declarationDIV"]/table/tbody/tr'
TREE_ROOT = 'xpath=//*[@id="outLineTree"]/font/div/table/tbody/tr[1]/td/div/font/b/span'
IMPORT_LINK = 'xpath=//*[@id="smoothmenu1"]/ul/li[3]/ul/li[5]/a'
LOGIN_AREA = 'xpath=/html/body/map/area'
UPLOAD_BTN = 'xpath=/html/body/table/tbody/tr[4]/td[2]/div/form/table/tbody/tr/td/table/tbody/tr[5]/td[2]/input[2]'
REFRESH_BTN = '#refreshInvBTN'
REF_NO = '#referenceNo'               # Reference No. ของใบขน เช่น QENX000000019 (มีตั้งแต่กด New)
SEARCH_REF = 'input[name="sREF"]'     # หน้ารายการใบขน: ช่อง Reference No.
SEARCH_BTN = '#refreshBTN'            # หน้ารายการใบขน: ปุ่ม Search
BUSY_CELL = 'xpath=//*[@id="mybody"]/center/table/tbody/tr/td[2]'
DONE_IMG = 'xpath=/html/body/center/table/tbody/tr/td[2]/center/img'
IMPORT_OK = re.compile(r'success\W*(?:\w+\W+){0,3}?please\s+check\s+your\s+invoice', re.I)
IMPORT_TIMEOUT = 180                  # วินาทีที่รอข้อความ success หลังกด Import (invoice ใหญ่ใช้เวลา)


class NetbayError(Exception):
    pass


def upload(csv_path, bl_no, totals, s, log=print, wait_close=None, until='review', on_step=None, info=None):
    """
    s = NetbaySettings  totals = ยอดรวมจาก netbay_csv.totals()
    until   = 'review' ทำครบแล้วหยุดให้คนตรวจ | 'import' จบหลัง Import สำเร็จ (worker)
    on_step = เรียก on_step(page) หลังจบแต่ละขั้น (worker ใช้ถ่ายภาพหน้าจอส่งขึ้น ERP)
    info    = dict ที่จะได้ ref_no / decl_id ของใบขนที่สร้าง — มีค่าแม้งานล้มกลางทาง
    คืน Reference No. ของใบขน
    """
    _check(s)
    if wait_close is None:
        wait_close = until == 'review' and not s.headless
    info = {} if info is None else info
    dialogs = info.setdefault('dialogs', [])
    step = on_step or (lambda page: None)

    def on_dialog(d):
        msg = ' '.join(d.message.split())
        dialogs.append(msg)
        log('  NETBAY แจ้ง: %s' % msg[:300])
        d.accept()                                   # alert ทุกอันกด OK เหมือนโปรแกรมเดิม

    with sync_playwright() as p:
        browser = _launch(p, s)
        try:
            context = browser.new_context(no_viewport=not s.headless)
            context.set_default_timeout(30_000)
            context.on('dialog', on_dialog)
            page = context.new_page()
            log('login NETBAY ...')
            import_url = login(page, s)
            log('สร้างใบขนใหม่ %s และกรอกหัวใบขน BL %s ...' % (s.declaration_type, bl_no))
            new_declaration(page, import_url, s, bl_no, totals, info)
            log('  ใบขน Reference No. %s' % info['ref_no'])
            step(page)
            log('แนบไฟล์ CSV (Add Invoice → Import) ...')
            ok = import_csv(page, csv_path, dialogs)
            log('  NETBAY: %s' % ok)
            step(page)
            if until == 'review':
                refresh_invoices(page, log)
                log('รวมน้ำหนัก / อากร / VAT จากทุก invoice ...')
                fill_totals(page, log)
                step(page)
                log('คำนวณใหม่ (Re-avg / ภาษี / CIF) ...')
                recalculate(page, log)
                step(page)
                log('เสร็จแล้ว — ตรวจข้อมูลบนหน้าจอ NETBAY แล้วกด Save เอง จากนั้นปิดหน้าต่างเบราว์เซอร์')
            if wait_close:
                page.wait_for_event('close', timeout=0)
        finally:
            browser.close()
    return info['ref_no']


def _check(s):
    if not (s.url and s.username and s.password):
        raise NetbayError('ยังไม่ได้ตั้งค่า url/username/password ของ NETBAY ใน config.ini')


def _launch(p, s):
    args = ['--unsafely-treat-insecure-origin-as-secure=' + s.url]
    if not s.headless:
        args.append('--start-maximized')
    try:
        return p.chromium.launch(channel='chrome', headless=s.headless, args=args)   # Google Chrome ที่ติดตั้งในเครื่อง
    except Exception:
        return p.chromium.launch(headless=s.headless, args=args)


def type_into(loc, text, click=False):
    """ล้างช่อง แล้วพิมพ์ทีละตัว (ให้ event ของหน้าเว็บทำงานเหมือนคนพิมพ์) จนค่าในช่องตรง

    click=True ใช้กับช่องที่มี input mask (วันที่ __-__-____): คลิกแล้วกด Home ให้ cursor อยู่ต้นช่อง
    ไม่งั้นตัวเลขไปลงตรงจุดที่คลิก (กลางช่อง) ได้ __-__-2010
    """
    text = str(text)
    for _ in range(5):
        loc.fill('')
        if click:
            loc.click()
            loc.press('Home')
        loc.press_sequentially(text)
        if loc.input_value() == text:
            return
    raise NetbayError('กรอกค่า %r ไม่สำเร็จ (ในช่องเป็น %r)' % (text, loc.input_value()))


def login(page, s):
    page.goto(s.url.rstrip('/') + '/')
    page.locator('#user').fill(s.username)
    page.locator('#passwd').fill(s.password)
    page.locator(LOGIN_AREA).first.dispatch_event('click')   # ปุ่ม login เป็น <area> ของ image map
    link = page.locator(IMPORT_LINK)
    try:
        link.wait_for(state='attached', timeout=15_000)
    except PWTimeout:
        page.locator('#passwd').press('Enter')
        try:
            link.wait_for(state='attached')
        except PWTimeout:
            raise NetbayError('login ไม่สำเร็จ หรือไม่พบเมนูหน้า import — ตรวจ username/password') from None
    href = link.evaluate('a => a.href')
    if not href:
        raise NetbayError('ไม่พบลิงก์หน้า import — หน้าเว็บ NETBAY อาจเปลี่ยน')
    return href


def new_declaration(page, import_url, s, bl_no, totals, info=None):
    page.goto(import_url)
    page.locator('#newBTN').click()
    page.locator(TREE_ROOT).wait_for(state='attached')
    f = page.frame_locator('#detailfrm')
    if info is not None:            # กด New แล้ว NETBAY สร้างใบขนทันที จำเลขไว้ก่อน เผื่อขั้นต่อไปล้ม
        info['ref_no'] = f.locator(REF_NO).input_value()
        frame = page.frame('detailfrm')
        m = re.search(r'ImDclCtrl=(\d+)', frame.url if frame else '')
        info['decl_id'] = m.group(1) if m else ''
        if not info['ref_no']:
            raise NetbayError('ไม่พบ Reference No. ของใบขนที่สร้าง — หน้าเว็บ NETBAY อาจเปลี่ยน')
    f.locator('xpath=//*[@id="declTypeID"]/font/select').select_option(value=s.declaration_type)
    pick_importer(f, s)
    f.locator(D + '[5]/td[2]/select').select_option(value='1')
    f.locator(D + '[5]/td[4]/select').select_option(value='9')
    type_into(f.locator(D + '[6]/td[2]/input'), s.vessel)
    type_into(f.locator('#ins_voyage'), s.voyage)
    type_into(f.locator('#ins_arrivalDate'), datetime.date.today().strftime('%d-%m-%Y'), click=True)
    type_into(f.locator(D + '[7]/td[4]/input'), bl_no)
    type_into(f.locator(D + '[8]/td[2]/input'), s.origin_country)
    type_into(f.locator(D + '[8]/td[4]/input'), s.origin_country)
    type_into(f.locator(D + '[9]/td[4]/input'), s.release_port)
    type_into(f.locator(D + '[10]/td[2]/font[1]/input[1]'), totals['package_amount'])
    type_into(f.locator(D + '[10]/td[2]/font[1]/input[2]'), totals['package_unit'])
    type_into(f.locator(D + '[12]/td[2]/font/input[1]'), totals['gross_weight'])
    type_into(f.locator(D + '[13]/td[2]/font/input[1]'), totals['gross_weight'])
    type_into(f.locator(D + '[19]/td[2]/font/input[1]'), totals['price'])
    type_into(f.locator(D + '[19]/td[2]/font/input[2]'), totals['currency'])


def pick_importer(f, s):
    """พิมพ์ชื่อบริษัท กดลูกศรลง ดับเบิลคลิกรายการแรก จนช่องผู้นำเข้าขึ้นชื่อที่ถูกต้อง"""
    box = f.locator(D + '[2]/td[2]/input')
    name = f.locator('xpath=//*[@id="importerDetail"]/font/input[1]')
    for _ in range(10):
        type_into(box, s.importer_search)
        box.press('ArrowDown')
        f.locator('xpath=//*[@id="tr1"]/td[3]').dblclick()
        if name.input_value() == s.importer_name:
            return
    raise NetbayError('เลือกบริษัทผู้นำเข้าไม่สำเร็จ (คาดว่า %r)' % s.importer_name)


def click_and_wait_frame(page, locator, timeout=30_000):
    """คลิกแล้วรอให้ iframe detailfrm โหลดหน้าใหม่เสร็จ (ไม่โหลดหน้าใหม่ หรือ NETBAY เปลี่ยน iframe ทั้งอัน ก็ไปต่อ)"""
    frame = page.locator('#detailfrm').element_handle().content_frame()
    try:
        with frame.expect_navigation(timeout=timeout):
            locator.click()
    except PWTimeout:
        pass
    except PWError as e:
        if 'detached' not in str(e):
            raise


def _frame_texts(page):
    """ข้อความบนหน้าจอทุก frame — frame ที่กำลังโหลดใหม่หรือถูกถอดออกให้ข้ามไป"""
    out = []
    for fr in page.frames:
        try:
            out.append(fr.evaluate('() => document.body ? document.body.innerText : ""') or '')
        except PWError:
            pass
    return out


def import_csv(page, csv_path, dialogs=(), timeout=None):
    """Add Invoice -> File for import (เลือก CSV) -> Import  แล้วรอจน NETBAY ขึ้น success please check your invoice"""
    timeout = timeout or IMPORT_TIMEOUT
    f = page.frame_locator('#detailfrm')
    f.locator('#addInvoice').click()
    f.locator('xpath=//*[@id="maptypeDiv2"]/input').set_input_files(csv_path)
    try:
        f.locator(UPLOAD_BTN).click(no_wait_after=True)
    except PWError as e:          # หน้าเปลี่ยนระหว่างกด — ปุ่มถูกกดไปแล้ว ดูผลจากข้อความต่อ
        if 'detached' not in str(e):
            raise
    end = time.time() + timeout
    while time.time() < end:
        for text in list(dialogs) + _frame_texts(page):
            m = IMPORT_OK.search(text)
            if m:
                return ' '.join(m.group(0).split())
        time.sleep(1)
    seen = ' '.join(' | '.join(t for t in _frame_texts(page) if t.strip()).split())
    raise NetbayError('ไม่เห็นข้อความ "success please check your invoice" หลังกด Import ภายใน %d วินาที'
                      ' — หน้าจอขึ้นว่า: %s' % (timeout, seen[:300] or '-'))


def refresh_invoices(page, log):
    """กด Refresh ให้รายการ invoice ที่เพิ่ง Import ขึ้น แล้วกลับหน้าหัวใบขน"""
    refresh = page.frame_locator('#detailfrm').locator(REFRESH_BTN)
    try:
        refresh.wait_for(state='visible', timeout=15_000)
    except PWTimeout:
        log('  ไม่พบปุ่ม Refresh หลัง Import — กด Refresh เองบนหน้าจอ')
    else:
        click_and_wait_frame(page, refresh, timeout=10_000)
    page.locator(TREE_ROOT).click()


def set_from_all_invoices(page, f, xpath):
    """ดับเบิลคลิกช่องรวมยอด -> หน้าต่างใหม่ -> ALL_INVOICE -> SetValue -> กด OK"""
    with page.context.expect_page() as new:
        f.locator('xpath=' + xpath).dblclick()
    popup = new.value
    popup.wait_for_load_state()
    popup.locator('#ALL_INVOICE').click()
    with page.context.expect_event('dialog'):
        popup.locator('#SetValue').click()
    try:
        popup.wait_for_event('close', timeout=5_000)
    except PWTimeout:
        if not popup.is_closed():
            popup.close()


def fill_totals(page, log):
    f = page.frame_locator('#detailfrm')
    try:
        page.locator('xpath=//*[@id="dm0"]/ui/li[1]/a/span').click(timeout=10_000)
        set_from_all_invoices(page, f, '//*[@id="grossWeightSpan"]/input')
    except PWTimeout:
        log('  ข้ามการรวมน้ำหนัก (ไม่พบเมนู) — ทำอากร/VAT ต่อ')
    f.locator('#switchDutyBTN').click()
    set_from_all_invoices(page, f, '//*[@id="dutyInnerDiv"]/table/tbody/tr[7]/td[2]/font/input')
    set_from_all_invoices(page, f, '//*[@id="vatInnerDiv"]/table/tbody/tr[5]/td[2]/font/input')


def _wait_done(f, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        try:
            src = f.locator(DONE_IMG).get_attribute('src', timeout=1_000) or ''
            if src.split('/')[-1] == 'done.jpg':
                return True
        except PWTimeout:
            pass
        time.sleep(0.3)
    return False


def recalculate(page, log):
    f = page.frame_locator('#detailfrm')
    for button, name in (('#AutoRecalc', 'Re-avg'), ('#AutoRecalTax', 'คำนวณภาษี'), ('#sumCif2Inv', 'รวม CIF')):
        click_and_wait_frame(page, page.locator(button), timeout=15_000)
        f.locator(BUSY_CELL).wait_for(state='attached')
        if not _wait_done(f):
            log('  ไม่เห็นสัญญาณเสร็จของ %s ภายใน 10 วินาที — ตรวจบนหน้าจอ' % name)
    page.locator(TREE_ROOT).click()


# ---------------------------------------------------------------- เปิดใบขนจาก Reference No.

def find_declaration(page, list_url, ref):
    """หน้ารายการใบขน: ค้นหาตาม Reference No.  คืนเลขภายในของใบขน (ImDclCtrl) หรือ None"""
    page.goto(list_url)
    page.locator(SEARCH_REF).fill(ref)
    try:
        with page.expect_navigation(timeout=30_000):
            page.locator(SEARCH_BTN).click()
    except PWTimeout:
        pass
    hit = page.locator('img[id^="statusPic"][value="%s"]' % ref)
    if hit.count() == 0:
        return None
    return hit.first.get_attribute('id')[len('statusPic'):]


def _banner(page, message):
    """แถบแจ้งด้านบนหน้าเว็บ NETBAY (alert ใช้ไม่ได้ เพราะ Playwright ปิด dialog เอง)"""
    try:
        page.evaluate('''m => { const d = document.createElement('div'); d.textContent = m;
            d.style.cssText = 'position:sticky;top:0;z-index:9999;padding:12px;background:#b0402b;color:#fff;font:16px sans-serif';
            (document.body || document.documentElement).prepend(d); }''', message[:500])
    except PWError:
        pass


def _chrome_path(p):
    """Google Chrome ที่ติดตั้งในเครื่อง ไม่มีก็ใช้ Chromium ของ Playwright"""
    for path in ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                 os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe'),
                 os.path.expandvars(r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe'),
                 os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
                 shutil.which('google-chrome') or ''):
        if path and os.path.isfile(path):
            return path
    return p.chromium.executable_path


def _free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def open_declaration(ref, s, log=print, profiles_dir=None, keep_open=True):
    """
    ลิงก์ Ref No. บน ERP-KOLA: เปิด Chrome -> login -> Import -> ค้นหา Reference No. -> เปิดใบขนนั้น

    เปิด Chrome ธรรมดา (โปรไฟล์ชั่วคราว) แล้วต่อเข้าไปคุมเฉพาะตอน login และค้นหา
    เสร็จแล้วปล่อย — หน้าต่างเป็น Chrome ปกติ คนตรวจใช้ต่อได้ทุกอย่าง (dialog ยืนยันของ NETBAY ขึ้นตามปกติ)
    คืนเลขภายในของใบขน หรือ None ถ้าไม่พบ (หน้ารายการขึ้นแถบแจ้งให้เห็น)
    """
    _check(s)
    profiles_dir = profiles_dir or os.path.join(tempfile.gettempdir(), 'kola-netbay')
    os.makedirs(profiles_dir, exist_ok=True)
    for name in os.listdir(profiles_dir):          # โปรไฟล์ของรอบก่อน ๆ ที่เกิน 1 วัน
        path = os.path.join(profiles_dir, name)
        if os.path.isdir(path) and os.path.getmtime(path) < time.time() - 86400:
            shutil.rmtree(path, ignore_errors=True)
    profile = tempfile.mkdtemp(prefix='p-', dir=profiles_dir)
    port = _free_port()

    with sync_playwright() as p:
        args = [_chrome_path(p), '--remote-debugging-port=%d' % port, '--user-data-dir=' + profile,
                '--no-first-run', '--no-default-browser-check',
                '--unsafely-treat-insecure-origin-as-secure=' + s.url]
        args += ['--headless=new'] if s.headless else ['--start-maximized']
        proc = subprocess.Popen(args + ['about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = page = None
        try:
            for _ in range(60):
                try:
                    browser = p.chromium.connect_over_cdp('http://127.0.0.1:%d' % port)
                    break
                except PWError:
                    time.sleep(0.25)
            if browser is None:
                raise NetbayError('เปิด Chrome ไม่สำเร็จ')
            context = browser.contexts[0]
            context.set_default_timeout(30_000)
            page = context.pages[0] if context.pages else context.new_page()
            log('login NETBAY ...')
            list_url = login(page, s)
            log('ค้นหา Reference No. %s ...' % ref)
            decl_id = find_declaration(page, list_url, ref)
            if decl_id:
                page.evaluate('id => editID(id)', decl_id)
                page.locator('#detailfrm').wait_for(state='attached')
                log('เปิดใบขน %s แล้ว' % ref)
            else:
                _banner(page, 'ไม่พบใบขน Reference No. %s ใน NETBAY — ค้นหาเองอีกครั้งในหน้านี้' % ref)
                log('ไม่พบใบขน %s' % ref)
            return decl_id
        except Exception as e:      # เปิดจากลิงก์ไม่มีหน้าต่าง Terminal — บอกเหตุผลบนหน้าจอ Chrome
            if page is not None:
                _banner(page, 'เปิดใบขน %s ไม่สำเร็จ: %s' % (ref, e))
            raise
        finally:
            if browser is not None:
                browser.close()           # ต่อแบบ CDP: แค่ปล่อยการควบคุม หน้าต่าง Chrome ยังอยู่
            if not keep_open:
                proc.terminate()
