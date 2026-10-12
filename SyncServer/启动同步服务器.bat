@echo off
chcp 65001 >nul
cd /d %~dp0
echo 正在停止旧的同步服务器实例...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match 'sync_server' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
python sync_server.py %~dp0..\..\音乐集合
pause