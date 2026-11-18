@echo off
rem Downloads word frequency lists (hermitdave/FrequencyWords, OpenSubtitles 2018, CC-BY-SA 4.0)
rem and saves them as words_uk.txt, words_ru.txt, words_en.txt next to this file.
rem The FULL lists are trimmed to the 300000 most frequent words. If a full list cannot be
rem downloaded, the 50k list is used instead. The full lists are large: it may take a few minutes.
cd /d "%~dp0"
set BASE=https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018
for %%L in (uk ru en) do powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing '%BASE%/%%L/%%L_full.txt' -OutFile 'tmp_%%L.txt'; Get-Content 'tmp_%%L.txt' -Encoding UTF8 -TotalCount 300000 | Set-Content -Encoding UTF8 'words_%%L.txt'; Remove-Item 'tmp_%%L.txt' } catch { Invoke-WebRequest -UseBasicParsing '%BASE%/%%L/%%L_50k.txt' -OutFile 'words_%%L.txt' }"
echo.
if exist words_uk.txt if exist words_ru.txt if exist words_en.txt (echo Done: words_uk.txt, words_ru.txt, words_en.txt) else (echo Something failed, check your internet connection)
echo Put these files next to LayoutSwitcher.exe and restart the program.
pause
