@echo off
chcp 65001 >nul
echo ============================================================
echo   📦 视频工作台 — 一键打包桌面版 exe（无黑窗）
echo ============================================================
echo.

cd /d "%~dp0"

if not exist venv (
    echo [1/3] 创建虚拟环境...
    python -m venv venv
    call venv\Scripts\activate.bat
) else (
    echo [1/3] 使用已有 venv
    call venv\Scripts\activate.bat
)

echo.
echo [2/3] 安装依赖...
pip install pyinstaller pywebview flask waitress PyYAML openpyxl watchdog opencv-python numpy Pillow --quiet

echo.
echo [3/3] 打包中（约 30-60 秒）...
pyinstaller --onefile --noconsole ^
    --name "视频工作台" ^
    --collect-data pywebview ^
    --collect-submodules clr_loader ^
    main_desktop.py

if %ERRORLEVEL%==0 (
    echo.
    echo ============================================================
    echo   ✅ 打包成功！
    echo   可执行文件: dist\视频工作台.exe
    echo   双击即可运行，无 CMD 黑窗
    echo ============================================================
) else (
    echo.
    echo ❌ 打包失败，检查错误信息
)

echo.
pause
