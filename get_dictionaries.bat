@echo off
rem Downloads Hunspell dictionaries (uk_UA, ru_RU, en_US) from the LibreOffice dictionaries repository
rem into the "dictionaries" folder next to this file. See the licence files in that repository.
cd /d "%~dp0"
if not exist dictionaries mkdir dictionaries
set BASE=https://raw.githubusercontent.com/LibreOffice/dictionaries/master
powershell -NoProfile -Command "foreach ($f in @('uk_UA/uk_UA.aff','uk_UA/uk_UA.dic','ru_RU/ru_RU.aff','ru_RU/ru_RU.dic','en/en_US.aff','en/en_US.dic')) { $n = Split-Path $f -Leaf; Write-Host ('Downloading ' + $n); try { Invoke-WebRequest -UseBasicParsing ($env:BASE + '/' + $f) -OutFile ('dictionaries\' + $n) } catch { Write-Host ('FAILED: ' + $n) } }"
echo.
if exist dictionaries\uk_UA.dic if exist dictionaries\ru_RU.dic if exist dictionaries\en_US.dic (echo Done: dictionaries folder is ready) else (echo Some files are missing, check your internet connection)
echo Put the "dictionaries" folder next to LayoutSwitcher.exe and restart the program.
pause
