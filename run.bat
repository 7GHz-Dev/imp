@echo off
rem เปิดหน้าเว็บโปรแกรม (ปิดหน้าต่างนี้ = ปิดโปรแกรม)
chcp 65001 >nul
cd /d %~dp0
.venv\Scripts\python app.py
pause
