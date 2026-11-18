#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Завантажує дані для збірки: частотні списки слів і словники Hunspell.

Запускається під час збірки інсталятора (GitHub Actions або build.bat), а не самою програмою:
сама LayoutSwitcher не має жодних мережевих викликів.

  words_uk.txt, words_ru.txt, words_en.txt
      hermitdave/FrequencyWords, OpenSubtitles 2018 (CC-BY-SA 4.0).
      Беруться 300000 найчастіших слів; якщо повний список недоступний, береться список на 50 тисяч.
  dictionaries/{uk_UA,ru_RU,en_US}.{aff,dic}
      LibreOffice dictionaries (ліцензії дивіться в тому репозиторії).

Уже наявні файли пропускаються. Ключ --force завантажує все заново.
"""
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WORDS_BASE = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018"
DICT_BASE = "https://raw.githubusercontent.com/LibreOffice/dictionaries/master"
WORDS_LIMIT = 300000
DICT_FILES = ["uk_UA/uk_UA.aff", "uk_UA/uk_UA.dic", "ru_RU/ru_RU.aff", "ru_RU/ru_RU.dic",
              "en/en_US.aff", "en/en_US.dic"]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "LayoutSwitcher-build"})
    return urllib.request.urlopen(req, timeout=120)


def get_words(lang):
    out = os.path.join(HERE, f"words_{lang}.txt")
    for kind, limit in (("full", WORDS_LIMIT), ("50k", None)):
        url = f"{WORDS_BASE}/{lang}/{lang}_{kind}.txt"
        try:
            print(f"Завантаження {url}")
            lines = []
            with fetch(url) as r:
                for raw in r:
                    lines.append(raw.decode("utf-8-sig").rstrip("\r\n"))
                    if limit and len(lines) >= limit:
                        break
            if len(lines) < 10000:
                raise ValueError(f"замало рядків: {len(lines)}")
            with open(out, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines) + "\n")
            print(f"  {out}: {len(lines)} слів ({kind})")
            return
        except Exception as e:
            print(f"  не вдалося ({kind}): {e}")
    sys.exit(f"ПОМИЛКА: не вдалося отримати words_{lang}.txt")


def get_dict(path):
    name = os.path.basename(path)
    out = os.path.join(HERE, "dictionaries", name)
    url = f"{DICT_BASE}/{path}"
    print(f"Завантаження {url}")
    try:
        with fetch(url) as r:
            data = r.read()
    except Exception as e:
        sys.exit(f"ПОМИЛКА: {name}: {e}")
    if len(data) < 1000:
        sys.exit(f"ПОМИЛКА: {name}: файл підозріло малий ({len(data)} байт)")
    with open(out, "wb") as f:
        f.write(data)
    print(f"  {out}: {len(data)} байт")


def main():
    force = "--force" in sys.argv
    os.makedirs(os.path.join(HERE, "dictionaries"), exist_ok=True)
    for lang in ("uk", "ru", "en"):
        if force or not os.path.exists(os.path.join(HERE, f"words_{lang}.txt")):
            get_words(lang)
    for p in DICT_FILES:
        if force or not os.path.exists(os.path.join(HERE, "dictionaries", os.path.basename(p))):
            get_dict(p)
    print("Готово: words_*.txt і dictionaries/ на місці.")


if __name__ == "__main__":
    main()
