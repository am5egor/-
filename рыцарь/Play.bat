@echo off
cd /d "%~dp0"
set "PY=C:\Users\1\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if exist "%PY%" (
    "%PY%" knight_game.py
) else (
    py knight_game.py
)
if errorlevel 1 pause
