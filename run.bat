@echo off
cd /d "%~dp0"
:restart
echo [%time%] 啟動中...
node server.js
echo [%time%] 進程退出，5 秒後重啟...
timeout /t 5 /nobreak >nul
goto restart
