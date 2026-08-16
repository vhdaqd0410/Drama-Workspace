@echo off
pyinstaller ^
--noconsole ^
--name DramaTool ^
--icon assets\icon.ico ^
src\main.py
pause
