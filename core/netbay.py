# -*- coding: utf-8 -*-
"""
ส่ง CSV เข้า NETBAY ด้วย Playwright

ขั้นตอนและ XPath ยกมาจาก csv_to_netbay() ของโปรแกรมเดิม (Selenium):
  login -> หน้า import -> สร้างใบขนใหม่ (610) -> กรอกหัวใบขน -> แนบ CSV
  -> รวมน้ำหนัก/อากร/VAT จากทุก invoice -> คำนวณใหม่
หน้าเว็บ imp: หยุดก่อนกด Save ให้คนตรวจบนหน้าจอ แล้วปิดหน้าต่างเอง
worker.py (save=True): กด F12 [Save] ให้เอง — ไม่กด Send to Customs ไม่ว่ากรณีใด
"""
import datetime
import re
import time

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

D = 'xpath=//*[@id="declarationDIV"]/table/tbody/tr'
TREE_ROOT = 'xpath=//*[@id="outLineTree"]/font/div/table/tbody/tr[1]/td/div/font/b/span'
IMPORT_LINK = 'xpath=//*[@id="smoothmenu1"]/ul/li[3]/ul/li[5]/a'
LOGIN_AREA = 'xpath=/html/body/map/area'
UPLOAD_BTN = 'xpath=/html/body/table/tbody/tr[4]/td[2]/div/form/table/tbody/tr/td/table/tbody/tr[5]/td[2]/input[2]'
REFRESH_BTN = '#refreshInvBTN'
SAVE_BTN = '#saveBTN'                 # F12 [Save] ในหน้าหัวใบขน
REF_NO = '#referenceNo'               # Reference No. ของใบขน เช่น QENX000000019 (มีตั้งแต่กด New)
BUSY_CELL = 'xpath=//*[@id="mybody"]/center/table/tbody/tr/td[2]'
DONE_IMG = 'xpath=/html/body/center/table/tbody/tr/td[2]/center/img'


class NetbayError(Exception):
    pass


def upload(csv_path, bl_no, totals, s, log=print, wait_close=None, save=False, on_step=None, info=None):
    """
    s = NetbaySettings  totals = ยอดรวมจาก netbay_csv.totals()
    save    = กด Save ให้เองหลังคำนวณใหม่ (worker ที่ไม่มีคนเฝ้าหน้าจอ)
    on_step = เรียก on_step(page) หลังจบแต่ละขั้น (worker ใช้ถ่ายภาพหน้าจอส่งขึ้น ERP)
    info    = dict ที่จะได้ ref_no / decl_id ของใบขนที่สร้าง — มีค่าแม้งานล้มกลางทาง
    คืน Reference No. ของใบขน
    """
    if not (s.url and s.username and s.password):
        raise NetbayError('ยังไม่ได้ตั้งค่า url/username/password ของ NETBAY ใน config.ini')
    if wait_close is None:
        wait_close = not s.headless
    info = {} if info is None else info
    step = on_step or (lambda page: None)

    def on_dialog(d):
        log('  NETBAY แจ้ง: %s' % ' '.join(d.message.split())[:300])
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
            log('แนบไฟล์ CSV (Add Invoice → Import → Refresh) ...')
            attach_csv(page, csv_path, log)
            step(page)
            log('รวมน้ำหนัก / อากร / VAT จากทุก invoice ...')
            fill_totals(page, log)
            step(page)
            log('คำนวณใหม่ (Re-avg / ภาษี / CIF) ...')
            recalculate(page, log)
            step(page)
            if save:
                log('กด Save ...')
                save_declaration(page)
                step(page)
                log('บันทึกใบขน %s แล้ว' % info['ref_no'])
            else:
                log('เสร็จแล้ว — ตรวจข้อมูลบนหน้าจอ NETBAY แล้วกด Save เอง จากนั้นปิดหน้าต่างเบราว์เซอร์')
            if wait_close:
                page.wait_for_event('close', timeout=0)
        finally:
            browser.close()
    return info['ref_no']


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
    """คลิกแล้วรอให้ iframe detailfrm โหลดหน้าใหม่เสร็จ (ถ้าไม่โหลดหน้าใหม่ก็ไปต่อ)"""
    frame = page.locator('#detailfrm').element_handle().content_frame()
    try:
        with frame.expect_navigation(timeout=timeout):
            locator.click()
    except PWTimeout:
        pass


def attach_csv(page, csv_path, log):
    """Add Invoice -> File for import (เลือก CSV) -> Import -> Refresh"""
    f = page.frame_locator('#detailfrm')
    f.locator('#addInvoice').click()
    f.locator('xpath=//*[@id="maptypeDiv2"]/input').set_input_files(csv_path)
    click_and_wait_frame(page, f.locator(UPLOAD_BTN))
    refresh = f.locator(REFRESH_BTN)
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


def save_declaration(page):
    """กด F12 [Save] ที่หน้าหัวใบขน แล้วรอหน้าโหลดใหม่"""
    f = page.frame_locator('#detailfrm')
    button = f.locator(SAVE_BTN)
    try:
        button.wait_for(state='visible', timeout=15_000)
    except PWTimeout:                # ยังอยู่หน้าอื่น กลับไปหน้าหัวใบขนก่อน
        page.locator(TREE_ROOT).click()
        button.wait_for(state='visible')
    click_and_wait_frame(page, button, timeout=60_000)
    f.locator(REF_NO).wait_for(state='attached')
