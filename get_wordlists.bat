@echo off
rem Завантажує words_uk.txt, words_ru.txt, words_en.txt (потрібен Python 3.9+)
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
%PY% fetch_data.py --force
pause
