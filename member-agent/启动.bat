@echo off
title 剪辑助手
cd /d "%~dp0"

set PY=
where py >nul 2>nul
if %errorlevel%==0 set PY=py
if "%PY%"=="" (
    where python >nul 2>nul
    if %errorlevel%==0 set PY=python
)

if "%PY%"=="" (
    echo [未检测到 Python] 请先双击 "安装.bat" 完成环境准备。
    pause
    exit /b 1
)

echo 正在启动剪辑助手...
%PY% member_agent.py
pause
