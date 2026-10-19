@echo off
rem ติดตั้งครั้งแรก:  setup.bat  [ไฟล์ db_random_engine.csv ที่ export จาก SQL Server]
chcp 65001 >nul
cd /d %~dp0

if not exist .venv (
    python -m venv .venv || goto :error
)
.venv\Scripts\python -m pip install -q -r requirements.txt || goto :error

if not exist config.ini (
    copy config.example.ini config.ini >nul
    echo สร้าง config.ini แล้ว - ใส่ username/password ของ NETBAY ในหัวข้อ [netbay]
)

if not "%~1"=="" (
    .venv\Scripts\python tools\import_db.py "%~1" || goto :error
)

echo.
echo ติดตั้งเสร็จ  เปิดโปรแกรมด้วย run.bat
goto :eof

:error
echo ติดตั้งไม่สำเร็จ
exit /b 1
