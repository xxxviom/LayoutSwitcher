@echo off
rem Build LayoutSwitcher.exe (needs Python 3.9+ from python.org)
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py

%PY% -m pip install --upgrade pyinstaller
if errorlevel 1 goto err
%PY% -m PyInstaller --onefile --noconsole --clean --name LayoutSwitcher layout_switcher.py
if errorlevel 1 goto err
copy /y blacklist.txt dist\ >nul

echo.
echo Done. Portable version: dist\LayoutSwitcher.exe, keep blacklist.txt next to it.
echo For an installer open installer.iss in Inno Setup 6 and click Compile.
pause
exit /b 0

:err
echo.
echo Build failed. See the messages above.
pause
exit /b 1
