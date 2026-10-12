@echo off
chcp 65001 >nul
cd /d "%~dp0"
python sync_server.py "F:\DeepSeek Workspace\时事分析\音乐集合"
pause
