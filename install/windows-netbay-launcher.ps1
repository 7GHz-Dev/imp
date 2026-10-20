# ติดตั้งตัวเปิดใบขนบน Windows — ให้เลข Ref No. บน ERP-KOLA กดแล้วเปิดใบขนใน NETBAY ได้
#
# ลงทะเบียนลิงก์ kola-netbay://open?ref=<Reference No.> ให้ผู้ใช้คนนี้ (ไม่ต้องใช้สิทธิ์ Administrator)
# กดลิงก์แล้วจะรัน open_ref.py ของ imp: เปิด Chrome -> login -> Import -> ค้นหา Ref No. -> เปิดใบขน
# ใช้ username/password NETBAY จาก config.ini ของ imp ในเครื่องนี้ · log: work\open_ref.log
#
# วิธีใช้: ดับเบิลคลิก windows-netbay-launcher.cmd ในโฟลเดอร์เดียวกันนี้
# ย้ายโฟลเดอร์ imp ไปที่อื่นแล้วต้องรันใหม่ เพราะลิงก์จำที่อยู่โฟลเดอร์ไว้
$ErrorActionPreference = 'Stop'

$imp = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pyw = Join-Path $imp '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pyw)) {
  Write-Host "ไม่พบ $pyw — รัน setup.bat ของ imp ก่อนแล้วรันไฟล์นี้ใหม่" -ForegroundColor Red
  exit 1
}
& (Join-Path $imp '.venv\Scripts\python.exe') -c "from core import config; s = config.load().netbay; assert s.username and s.password" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "ยังไม่มี username/password ของ NETBAY ใน $imp\config.ini — เปิดใบขนไม่ได้จนกว่าจะใส่" -ForegroundColor Yellow
}

$key = 'HKCU:\Software\Classes\kola-netbay'
New-Item -Force -Path $key | Out-Null
Set-ItemProperty -Path $key -Name '(Default)' -Value 'URL:KOLA NETBAY'
Set-ItemProperty -Path $key -Name 'URL Protocol' -Value ''
New-Item -Force -Path "$key\shell\open\command" | Out-Null
# pythonw = ไม่มีหน้าต่าง console
Set-ItemProperty -Path "$key\shell\open\command" -Name '(Default)' `
  -Value "`"$pyw`" `"$imp\open_ref.py`" `"%1`""

Write-Host "ติดตั้งแล้ว — กดเลข Ref No. บน ERP-KOLA แล้วจะเปิดใบขนใน NETBAY ด้วย imp ใน $imp" -ForegroundColor Green
Write-Host "log: $imp\work\open_ref.log"
Write-Host 'ครั้งแรกเบราว์เซอร์จะถามว่าจะเปิด KOLA NETBAY ไหม — ติ๊กอนุญาตเสมอแล้วกดเปิด'
