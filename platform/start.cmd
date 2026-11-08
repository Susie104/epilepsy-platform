@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-background.ps1" -OpenBrowser
if errorlevel 1 pause
