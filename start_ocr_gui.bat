@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 星火日历 · OCR 清洗本地服务
echo.
echo  正在启动本地服务：http://localhost:8000
echo.
where python >nul 2>&1
if %errorlevel%==0 (
  start "OCR清洗服务" cmd /k "python -m http.server 8000 --bind 127.0.0.1"
) else (
  where py >nul 2>&1
  if %errorlevel%==0 (
    start "OCR清洗服务" cmd /k "py -m http.server 8000 --bind 127.0.0.1"
  ) else (
    echo  [!] 未找到 python，请先安装 Python，或手动执行：
    echo      python -m http.server 8000
    pause
    exit /b 1
  )
)
timeout /t 2 /nobreak >nul
start "" "http://localhost:8000/tools/ocr_clean_gui.html"
