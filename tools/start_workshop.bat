@echo off
chcp 65001 >nul
set ROOT=%~dp0
if not exist "%ROOT%index.html" if exist "%ROOT%..\index.html" set "ROOT=%ROOT%.."
cd /d "%ROOT%"
set "ROOT=%CD%"
title 星火日历 · 工具台（OCR清洗/合并应用/详情丰富）
echo.
echo  正在启动本地服务：http://127.0.0.1:8001
echo  站点根目录：%ROOT%
echo.
where python >nul 2>&1
if %errorlevel%==0 (
  start "工具台服务" cmd /k "python tools\detail_server.py"
) else (
  where py >nul 2>&1
  if %errorlevel%==0 (
    start "工具台服务" cmd /k "py tools\detail_server.py"
  ) else (
    echo  [!] 未找到 python，请先安装 Python，或手动执行：
    echo      python tools\detail_server.py
    pause
    exit /b 1
  )
)
echo  等待服务就绪（最多 15 秒）…
set ok=
for /l %%i in (1,1,15) do (
  curl -s -o nul --max-time 1 http://127.0.0.1:8001/tools/workshop.html 2>nul
  if not errorlevel 1 ( set ok=1 & goto :up )
  timeout /t 1 /nobreak >nul
)
:up
if not defined ok (
  echo  [!] 服务未就绪：可能端口 8001 被占用或 Python 启动失败。
  echo      请查看「详情丰富服务」窗口的报错；浏览器仍会尝试打开页面。
)
start "" "http://127.0.0.1:8001/tools/workshop.html"
