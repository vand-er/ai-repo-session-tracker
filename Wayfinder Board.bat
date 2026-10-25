@echo off
rem Double-click to open the Wayfinder board without a console window.
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0wayfinder.py" %*
