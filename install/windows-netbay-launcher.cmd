@echo off
rem ดับเบิลคลิกไฟล์นี้เพื่อติดตั้งตัวเปิดใบขน (เรียก windows-netbay-launcher.ps1)
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-netbay-launcher.ps1"
pause
