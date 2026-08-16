# AI后期剪辑提成工具 — 环境安装脚本
# 在新电脑上运行：双击 install.bat 或在终端执行 install.bat

@echo off
chcp 65001 >nul
echo ============================================
echo   AI后期剪辑提成工具 — 环境安装
echo ============================================
echo.

:: 1. 检查 Python
echo [1/3] 检测 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 未找到 Python！请从 https://www.python.org/downloads/ 下载安装 Python 3.10+
    echo    安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)
python --version
echo ✅ Python 已就绪
echo.

:: 2. 安装依赖
echo [2/3] 安装 Python 依赖...
pip install openpyxl pandas fpdf2 -q
if errorlevel 1 (
    echo ⚠️ 依赖安装失败，尝试使用国内镜像...
    pip install openpyxl pandas fpdf2 -q -i https://pypi.tuna.tsinghua.edu.cn/simple
)
echo ✅ 依赖安装完成
echo.

:: 3. 创建必要目录
echo [3/3] 初始化目录...
if not exist "backup" mkdir backup
if not exist "output" mkdir output
if not exist "个人绩效卡片" mkdir 个人绩效卡片
echo ✅ 目录初始化完成
echo.

echo ============================================
echo   安装完成！双击 启动工具.vbs 启动程序
echo ============================================
pause
