@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo =========================================
echo   视频工作台 v2.0 - 启动中...
echo =========================================
python main.py
if %errorlevel% neq 0 (
    echo.
    echo 启动失败！按任意键退出...
    pause >nul
)
