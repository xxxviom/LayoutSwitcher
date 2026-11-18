@echo off
rem Збирає dist\LayoutSwitcher.exe та інсталятор dist\LayoutSwitcher-Setup.exe (потрібен Python 3.9+ з python.org)
rem Для інсталятора потрібен ще Inno Setup 6 (https://jrsoftware.org/isinfo.php); без нього збереться лише .exe
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py

%PY% fetch_data.py
if errorlevel 1 goto err
%PY% -m pip install --upgrade pyinstaller
if errorlevel 1 goto err
%PY% -m PyInstaller --onefile --noconsole --clean --name LayoutSwitcher layout_switcher.py
if errorlevel 1 goto err

set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if defined ISCC (
  "%ISCC%" installer.iss
  if errorlevel 1 goto err
  echo.
  echo Done. Installer: dist\LayoutSwitcher-Setup.exe
) else (
  echo.
  echo Done. Portable version: dist\LayoutSwitcher.exe, keep blacklist.txt, words_*.txt and dictionaries next to it.
  echo Inno Setup 6 not found, so the installer was not built.
)
pause
exit /b 0

:err
echo.
echo Build failed. See the messages above.
pause
exit /b 1
