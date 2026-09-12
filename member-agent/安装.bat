@echo off
title 剪辑助手 - 安装与环境检测
echo ============================================
echo   剪辑助手 - 安装与环境检测
echo ============================================
echo.

set PY=
where py >nul 2>nul
if %errorlevel%==0 set PY=py
if "%PY%"=="" (
    where python >nul 2>nul
    if %errorlevel%==0 set PY=python
)

if "%PY%"=="" (
    echo [未检测到 Python] 这台电脑还没有安装 Python。
    echo.
    echo 请按下面步骤安装 ^(只需一次^)：
    echo   1. 即将为你打开 Python 官网下载页
    echo   2. 下载并运行安装包
    echo   3. 安装时务必勾选 "Add Python to PATH"
    echo   4. 安装完成后，重新双击本文件
    echo.
    pause
    start https://www.python.org/downloads/
    exit /b 1
)

echo [检测到 Python] 正在检查版本...
%PY% -c "import sys; v=sys.version_info; print('  Python 版本: %%d.%%d.%%d' %% (v.major,v.minor,v.micro)); sys.exit(0 if v.major==3 and v.minor>=8 else 1)"
if errorlevel 1 (
    echo.
    echo [版本过低] 需要 Python 3.8 或更高版本。
    echo 请到官网安装新版：https://www.python.org/downloads/
    pause
    start https://www.python.org/downloads/
    exit /b 1
)

echo.
echo [环境正常] 本机 Python 已就绪，无需额外安装依赖。
echo.
echo 接下来请双击 "启动.bat" 开始使用。
echo.
pause
exit /b 0
