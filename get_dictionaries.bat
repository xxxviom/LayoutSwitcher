@echo off
rem Завантажує словники Hunspell у папку dictionaries (потрібен Python 3.9+)
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
%PY% fetch_data.py --force
pause
