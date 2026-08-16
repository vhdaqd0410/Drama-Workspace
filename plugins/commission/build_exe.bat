@echo off
chcp 65001 >nul
echo ========================================
echo  AI后期剪辑提成工具 - 打包单文件 exe
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] 检查 PyInstaller...
".venv\Scripts\python.exe" -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 未安装 PyInstaller，正在安装...
    ".venv\Scripts\python.exe" -m pip install pyinstaller
) else (
    echo PyInstaller 已安装。
)

echo.
echo [2/3] 开始打包（单文件模式）...
".venv\Scripts\python.exe" -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "提成工具" ^
    --add-data "src;src" ^
    --hidden-import openpyxl ^
    --hidden-import pandas ^
    --hidden-import matplotlib ^
    ai_commission_gui.py

echo.
echo [3/3] 打包完成！
echo 生成文件: dist\提成工具.exe
echo.
echo 提示：exe 首次运行需在旁放置 config.example.json 并复制为 config.json。
pause
