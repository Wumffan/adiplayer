@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo  Folia Player APK 打包工具
echo ========================================
echo.

set "PROJECT=%~dp0"
cd /d "%PROJECT%"

REM ====== 1. 检查必要工具 ======
echo [1/5] 检查环境...
where node >nul 2>&1
if errorlevel 1 ( echo ❌ 未找到 Node.js，请先装: https://nodejs.org & pause & exit /b 1 )
echo      Node.js ✅

where java >nul 2>&1
if errorlevel 1 (
  echo ❌ 未找到 Java JDK！
  echo    下载地址: https://adoptium.net/
  echo    安装后记得把 JDK 的 bin 目录加到 PATH
  pause & exit /b 1
)
echo      Java ✅

where adb >nul 2>&1
if errorlevel 1 (
  echo ⚠️ 未找到 ADB（仅安装 APK 到手机时需要）
) else (
  echo      ADB ✅
)

REM ====== 2. 提示输入部署域名 ======
echo.
echo [2/5] 输入线上部署域名
echo       （Railway: 比如 folia-player.up.railway.app）
echo       （Render: 比如 folia-player.onrender.com）
echo.
set /p DOMAIN=请输入域名（不要加 https://）: 
if "%DOMAIN%"=="" ( echo ❌ 域名不能为空 & pause & exit /b 1 )

REM ====== 3. 安装 Bubblewrap ======
echo.
echo [3/5] 安装 Bubblewrap...
if not exist "%PROJECT%\node_modules\.bin\bubblewrap.cmd" (
  call npm install -g @bubblewrap/cli 2>nul
  if errorlevel 1 ( call npm install @bubblewrap/cli --save-dev )
)
echo      Bubblewrap ✅

REM ====== 4. 生成配置 ======
echo.
echo [4/5] 生成 TWA 配置...
set "URL=https://%DOMAIN%"
echo 域名: %URL%

REM 替换 bubblewrap-config.json 中的占位符
powershell -Command "(Get-Content 'bubblewrap-config.json' -Raw) -replace 'YOUR-APP-DOMAIN', '%DOMAIN%' | Set-Content 'bubblewrap-config-local.json' -NoNewline"
copy /y "bubblewrap-config-local.json" "bubblewrap-config.json" >nul
del "bubblewrap-config-local.json"
echo      配置 ✅

REM ====== 5. 打包 APK ======
echo.
echo [5/5] 编译 APK（首次编译需下载 Android Build Tools，约 100MB）...
echo.
where bubblewrap >nul 2>&1
if errorlevel 1 (
  set "BUBBLEWRAP=%PROJECT%\node_modules\.bin\bubblewrap.cmd"
) else (
  set "BUBBLEWRAP=bubblewrap"
)

cd /d "%PROJECT%"
call %BUBBLEWRAP% init --manifest="%PROJECT%\bubblewrap-config.json" --directory="%PROJECT%\android-twa"
if errorlevel 1 ( echo ❌ init 失败 & pause & exit /b 1 )

call %BUBBLEWRAP% update --directory="%PROJECT%\android-twa"
call %BUBBLEWRAP% build --directory="%PROJECT%\android-twa"

if errorlevel 1 (
  echo.
  echo ❌ 编译失败！
  echo    如果提示缺少 Android SDK：
  echo    1. 安装 Android Studio: https://developer.android.com/studio
  echo    2. 打开 SDK Manager → 安装 Android SDK Platform 34 + Build-Tools
  echo    3. 设置环境变量 ANDROID_HOME
  pause & exit /b 1
)

REM ====== 完成 ======
echo.
echo ========================================
echo  ✅ APK 打包完成！
echo ========================================
echo.
echo  输出文件:
dir /b "%PROJECT%\android-twa\app\build\outputs\apk\release\*.apk" 2>nul
echo.

REM 尝试安装到连接的手机
where adb >nul 2>&1
if not errorlevel 1 (
  adb devices | findstr "device$" >nul
  if not errorlevel 1 (
    echo 正在安装到手机...
    for %%f in ("%PROJECT%\android-twa\app\build\outputs\apk\release\*.apk") do (
      adb install -r "%%f" && echo ✅ 已安装到手机！
    )
  )
)

pause
