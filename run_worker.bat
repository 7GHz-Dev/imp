@echo off
rem รับงาน "สร้าง Draft" จาก ERP-KOLA แล้วทำใบขนใน NETBAY  (ปิดหน้าต่างนี้ = ปิด worker)
chcp 65001 >nul
cd /d %~dp0
.venv\Scripts\python worker.py %*
pause
