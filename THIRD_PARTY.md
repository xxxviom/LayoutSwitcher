# Сторонні дані

Сам LayoutSwitcher не завантажує нічого з інтернету. Дані нижче завантажуються один раз під час
збірки інсталятора (`fetch_data.py`) і постачаються всередині `LayoutSwitcher-Setup.exe`.

- **Частотні списки слів** `words_uk.txt`, `words_ru.txt`, `words_en.txt`:
  [hermitdave/FrequencyWords](https://github.com/hermitdave/FrequencyWords), побудовані на корпусі
  OpenSubtitles 2018, ліцензія CC-BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/).
  Взято 300000 найчастіших слів на мову.
- **Словники Hunspell** `dictionaries/uk_UA`, `ru_RU`, `en_US`:
  [LibreOffice dictionaries](https://github.com/LibreOffice/dictionaries). Ліцензія кожного словника
  вказана в його папці в цьому репозиторії.
