@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo  网易云音乐 Folia Player 启动中...
echo  按 Ctrl+C 可停止
echo ========================================
node server.js
pause
