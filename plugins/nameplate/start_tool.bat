@echo off
title Script Parser Tool
cd /d "%~dp0"

REM Use pythonw to avoid console window. Fallback to python/py if not found.
set PY=pythonw
where pythonw >nul 2>nul
if errorlevel 1 (
    set PY=python
    where python >nul 2>nul
    if errorlevel 1 (
        set PY=py
        where py >nul 2>nul
        if errorlevel 1 (
            echo Python not found. Please install Python and check "Add to PATH".
            pause
            exit /b 1
        )
    )
)

start "" %PY% -X utf8 script_parser.py
