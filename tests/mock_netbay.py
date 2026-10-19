# -*- coding: utf-8 -*-
"""
NETBAY จำลองสำหรับทดสอบ core/netbay.py

โครงหน้าเว็บสร้างตาม XPath ที่โปรแกรมเดิมใช้ (ไม่ใช่หน้าจริงของ NETBAY)
ใช้ตรวจว่า Playwright ทำทุกขั้นได้: login, iframe, autocomplete, แนบไฟล์,
หน้าต่าง popup, alert และปุ่มคำนวณ  แล้วเก็บค่าที่กรอกไว้ใน state
"""
from flask import Flask, request

IMPORTER = 'บริษัท เเม่สอด ฟรีโซน จำกัด'


def create_mock():
    app = Flask(__name__)
    state = {'login': None, 'decl': None, 'upload': None, 'popups': [], 'recalc': []}
    app.state = state

    @app.get('/')
    def login_page():
        return '''<html><body>
<form method="post" action="/login"><input id="user" name="user"><input id="passwd" name="passwd" type="password">
<img src="/btn.gif" usemap="#m" width="60" height="20"></form>
<map name="m"><area shape="rect" coords="0,0,60,20" href="javascript:document.forms[0].submit()"></map>
</body></html>'''

    @app.post('/login')
    def login():
        state['login'] = (request.form['user'], request.form['passwd'])
        return '''<html><body><div id="smoothmenu1"><ul><li>a</li><li>b</li><li>c<ul>
<li>1</li><li>2</li><li>3</li><li>4</li><li><a href="/import?uid=1&amp;mode=imp">ใบขนขาเข้า</a></li>
</ul></li></ul></div></body></html>'''

    @app.get('/import')
    def import_page():
        return '''<html><body>
<button id="newBTN" onclick="document.getElementById('area').style.display='block';detailfrm.location='/decl'">New</button>
<div id="area" style="display:none">
 <div id="outLineTree"><font><div><table><tbody><tr><td><div><font><b>
   <span onclick="detailfrm.location='/header'">ROOT</span></b></font></div></td></tr></tbody></table></div></font></div>
 <div id="dm0"><ui><li><a href="#"><span onclick="detailfrm.location='/summary';return false">รวมยอด</span></a></li></ui></div>
 <button id="AutoRecalc" onclick="detailfrm.location='/busy?w=avg'">Re-avg</button>
 <button id="AutoRecalTax" onclick="detailfrm.location='/busy?w=tax'">Tax</button>
 <button id="sumCif2Inv" onclick="detailfrm.location='/busy?w=cif'">CIF</button>
 <iframe id="detailfrm" name="detailfrm" width="900" height="700"></iframe>
</div></body></html>'''

    @app.get('/decl')
    def decl():
        row = lambda cells: '<tr>%s</tr>' % ''.join('<td>%s</td>' % c for c in cells)
        rows = [
            row(['r1']),
            row(['ผู้นำเข้า', '<input name="importer_search" onkeydown="if(event.key==\'ArrowDown\')'
                 'document.getElementById(\'list\').style.display=\'block\'">']),
            row(['r3']), row(['r4']),
            row(['a', '<select name="s5a"><option value="0">0</option><option value="1">1</option></select>',
                 'b', '<select name="s5b"><option value="0">0</option><option value="9">9</option></select>']),
            row(['vessel', '<input name="vessel">']),
            row(['voyage', '<input id="ins_voyage" name="voyage">', 'bl', '<input name="bl">']),
            row(['origin', '<input name="origin1">', 'origin2', '<input name="origin2">']),
            row(['arrival', '<input id="ins_arrivalDate" name="arrival">', 'port', '<input name="release_port">']),
            row(['pkg', '<font><input name="pkg_amount"><input name="pkg_unit"></font>']),
            row(['r11']),
            row(['gw', '<font><input name="gw1"></font>']),
            row(['gw2', '<font><input name="gw2"></font>']),
        ] + [row(['r%d' % i]) for i in range(14, 19)] + [
            row(['price', '<font><input name="price"><input name="currency"></font>']),
        ]
        return '''<html><body>
<div id="declTypeID"><font><select name="decl_type"><option value="">-</option><option value="610">610</option></select></font></div>
<div id="declarationDIV"><table><tbody>%s</tbody></table></div>
<div id="list" style="display:none"><table><tbody>
 <tr id="tr1" ondblclick="document.querySelector('#importerDetail input').value='%s'"><td>1</td><td>0635561000645</td><td>MAESOT FREE ZONE</td></tr>
</tbody></table></div>
<div id="importerDetail"><font><input name="importer_name"></font></div>
<button id="addInvoice" onclick="save()">Add invoice</button>
<script>
function save() {
  const data = new URLSearchParams();
  document.querySelectorAll('input,select').forEach(e => data.append(e.name, e.value));
  fetch('/save_decl', {method: 'POST', body: data}).then(() => location = '/upload_form');
}
</script></body></html>''' % (''.join(rows), IMPORTER)

    @app.post('/save_decl')
    def save_decl():
        state['decl'] = request.form.to_dict()
        return 'ok'

    @app.get('/upload_form')
    def upload_form():
        return '''<html><body><table><tbody>
<tr><td>1</td></tr><tr><td>2</td></tr><tr><td>3</td></tr>
<tr><td>4</td><td><div><form method="post" action="/upload" enctype="multipart/form-data"><table><tbody><tr><td>
 <table><tbody>
  <tr><td>a</td></tr><tr><td>b</td></tr><tr><td>c</td></tr>
  <tr><td>file</td><td><div id="maptypeDiv2"><input type="file" name="file"></div></td></tr>
  <tr><td>go</td><td><input type="button" value="ยกเลิก"><input type="submit" value="Upload"></td></tr>
 </tbody></table>
</td></tr></tbody></table></form></div></td></tr>
</tbody></table></body></html>'''

    @app.post('/upload')
    def upload():
        f = request.files['file']
        state['upload'] = (f.filename, f.read())
        return '<html><body>uploaded</body></html>'

    @app.get('/header')
    def header():
        return '<html><body>header</body></html>'

    @app.get('/summary')
    def summary():
        pop = lambda w: "window.open('/allinv?f=%s','p','width=400,height=300')" % w
        trs = lambda n, cell: ''.join('<tr><td>%d</td><td>%s</td></tr>' % (i, cell if i == n else '')
                                      for i in range(1, n + 1))
        return '''<html><body>
<span id="grossWeightSpan"><input ondblclick="%s"></span>
<button id="switchDutyBTN" onclick="document.getElementById('duty').style.display='block'">อากร</button>
<div id="duty" style="display:none">
 <div id="dutyInnerDiv"><table><tbody>%s</tbody></table></div>
 <div id="vatInnerDiv"><table><tbody>%s</tbody></table></div>
</div></body></html>''' % (pop('gw'), trs(7, '<font><input ondblclick="%s"></font>' % pop('duty')),
                           trs(5, '<font><input ondblclick="%s"></font>' % pop('vat')))

    @app.get('/allinv')
    def allinv():
        return '''<html><body><input type="checkbox" id="ALL_INVOICE">
<button id="SetValue" onclick="fetch('/set?f=%s&all=' + document.getElementById('ALL_INVOICE').checked)
  .then(() => { alert('บันทึกแล้ว'); window.close(); })">Set</button></body></html>''' % request.args['f']

    @app.get('/set')
    def set_value():
        state['popups'].append((request.args['f'], request.args['all']))
        return 'ok'

    @app.get('/busy')
    def busy():
        return '''<html><body id="mybody"><center><table><tbody><tr><td>wait</td>
<td><center><img src="/wait.gif"></center></td></tr></tbody></table></center>
<script>setTimeout(() => fetch('/recalc?w=%s').then(() => document.querySelector('img').src = '/img/done.jpg'), 300)</script>
</body></html>''' % request.args['w']

    @app.get('/recalc')
    def recalc():
        state['recalc'].append(request.args['w'])
        return 'ok'

    return app
