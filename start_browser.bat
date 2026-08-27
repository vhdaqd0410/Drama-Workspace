@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo =========================================
echo   视频工作台 v3.4.0 - 网页版启动
echo   （会打开浏览器，顶部有地址栏）
echo   如需无地址栏的桌面版，请用 start.bat
echo =========================================
python main.py
if %errorlevel% neq 0 (
    echo.
    echo 启动失败！按任意键退出...
    pause >nul
)
