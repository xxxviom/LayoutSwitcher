#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LayoutSwitcher — автоперемикач розкладки EN / UK / RU для Windows 10/11.

Приватність і «без бекдорів» (код один файл, його можна прочитати):
  * лише стандартна бібліотека Python; жодних імпортів socket/urllib/http, жодних мережевих викликів;
  * словники беруться локально: перевірка правопису самої Windows (offline), словники Hunspell та
    файли words_*.txt поруч зі скриптом (за бажанням), ваші вивчені слова. n-грамна модель, пошук слів
    з опечатками й контекст речення рахуються в пам'яті;
  * «Навчити зі своїх документів» читає файли ЛИШЕ з папки, яку ви самі обрали в меню, і лише
    локально; слова, яких не знають словники, потрапляють у learned.txt;
  * САМОНАВЧАННЯ (можна вимкнути в меню трея): слово, яке ви тричі набрали правильно, але
    якого немає в словниках, потрапляє у learned.txt (звичайний текст: мова<TAB>слово).
    Лічильники повторів живуть лише в пам'яті. Не вчимося: у програмах з чорного списку,
    у класичних полях пароля, на словах з цифрами/змішаним регістром. Файл можна відкрити,
    відредагувати або повністю стерти з меню трея. Паролі в браузерах програма розпізнати
    не може, тому для браузера/менеджера паролів краще вимкнути навчання або додати
    програму в blacklist.txt;
  * в реєстр (HKCU\\...\\Run) пишеться лише рядок автозапуску, і тільки коли ви вмикаєте
    пункт «Запускати разом з Windows»; ще два перемикачі меню («Самонавчання» і «Прапор мови»)
    зберігаються в HKCU\\Software\\LayoutSwitcher;
  * хук миші бачить лише факт натискання кнопки (скинути слово при зміні позиції курсора).

Керування:
  «Виправляти на льоту» (меню трея, за замовчуванням вимкнено): не чекати пробілу, а виправляти, щойно
                     початок слова стає неможливим у поточній мові (потрібні words_*.txt);
  Pause            — вручну конвертувати слово (і ВЧИТИСЯ цього слова);
                     одразу після автокорекції Pause скасовує її й запам'ятовує, що слово було правильне
  Shift+Pause      — увімкнути/вимкнути автоперемикання
  Ctrl+Pause       — вийти
  Іконка в треї    — подвійний клік: пауза/відновлення; правий клік: меню

Автокорекція спрацьовує після пробілу, Enter або Tab: програма за мілісекунди вирішує, чи слово
набране не в тій розкладці. Якщо так, натискання «затримується», слово стирається й друкується
заново, розкладка перемикається, а все набране за цей час відтворюється в новій розкладці.
"""
import bisect
import codecs
import ctypes
import ctypes.wintypes as wt
import html
import math
import os
import queue
import re
import sys
import threading
import time
import uuid
import winreg
import zipfile
from array import array
from collections import Counter, deque, namedtuple

import winsound

FROZEN = getattr(sys, "frozen", False)     # True, якщо запущено як зібраний .exe
HERE = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))

# ───────────────────────────── Налаштування ─────────────────────────────
AUTO_ON_START = True
LEARN_ON_START = True        # самонавчання (перемикається в меню трея)
FLAG_ON_START = True         # прапор поточної мови замість кружечка в треї (перемикається в меню)
FLY_ON_START = False         # виправляти посеред слова, «на льоту» (перемикається в меню; потрібні words_*.txt)
FLY_MIN_START = 4            # скільки літер набрати, перш ніж виправляти на льоту: 3, 4 або 5
FLY_ALT_MIN = 6              # у скількох словах зі словника має зустрічатися такий початок у новій мові
WORDS_TOP = 60000            # скільки найчастіших слів із words_*.txt тримати з рангом (для 2–3-літерних слів, префіксів)
WORDS_MAX = 300000           # скільки слів читати з words_*.txt для перевірки «таке слово є» (компактно, 8 байт на слово)
MODEL_WORDS = 30000          # на скількох найчастіших словах вчити n-грамну модель
NGRAM_ORDER = 4              # порядок символьної n-грамної моделі (4 = контекст із 3 літер)
TYPO_WORDS = 60000           # скільки найчастіших слів використовувати для пошуку слів з однією опечаткою
CTX_WEIGHT = 0.12            # наскільки мова попередніх слів речення підсилює відповідну мову
DOC_MIN_COUNT = 2            # скільки разів слово має зустрітись у ваших документах, щоб його вивчити
DOC_MAX_NEW = 20000          # скільки нових слів максимум вивчати за один запуск навчання з документів
HUN_SLOW = 0.08              # якщо перевірка Hunspell довша (с) тричі поспіль — вимикаємо її
EN_FLAG = "us"               # який прапор показувати для англійської: "us" (США) або "gb" (Велика Британія)
LEARN_THRESHOLD = 3          # скільки разів слово треба набрати, щоб його запам'ятати
LEARN_MAX = 50000            # скільки вивчених слів максимум
USE_WINDOWS_SPELLCHECK = True  # словники перевірки правопису Windows (локальні, без мережі)
SPELL_SLOW = 0.08            # якщо один виклик правопису довший (с) — тричі поспіль — вимикаємо його
MIN_SHORT = 2                # найкоротше слово, яке ми розглядаємо (1 літеру не чіпаємо)
MIN_LETTERS = 4              # від такої довжини працюють моделі й перевірка правопису
SHORT_RANK = 2000            # слова з 2–3 літер зі словника беремо лише з топ-N за частотою
PREFERRED = "uk"             # кирилична мова за замовчуванням у разі нічиєї uk/ru
CUR_MAX, ALT_MIN, MARGIN = 0.25, 0.55, 0.30   # пороги впевненості
IDLE_RESET = 8.0             # секунд бездіяльності, після яких слово скидається
HOLD_LIMIT = 2.5             # аварійний ліміт (с): довше клавіатуру не «затримуємо»
KEY_DELAY = 0.004            # пауза (с) між введеними символами: деякі програми гублять швидкі події
UNDO_WINDOW = 8.0            # секунд після автокорекції, коли Pause її скасовує
EXCLUDED_EXE = {             # вбудований чорний список (доповнюється файлом blacklist.txt)
    "keepass.exe", "keepassxc.exe", "1password.exe", "bitwarden.exe",
}
BL_PATH = os.path.join(HERE, "blacklist.txt")
BL_TEMPLATE = """# Чорний список: програми, у яких автоперемикач нічого не виправляє і не вчиться.
# Одне ім'я exe-файлу в рядку; # починає коментар; регістр не важливий.
# Зміни підхоплюються автоматично, перезапуск не потрібен.
#
# keepass.exe
# code.exe
# game.exe
"""

# ───────────────────────────── Мовні дані ───────────────────────────────
KLID = {"en": "00000409", "uk": "00000422", "ru": "00000419"}
TAGS = {"en": "en-US", "uk": "uk-UA", "ru": "ru-RU"}
PRIMARY = {0x09: "en", 0x22: "uk", 0x19: "ru"}
ORDER = ["en", "uk", "ru"]
UK_ONLY, RU_ONLY = set("іїєґ"), set("ыэъё")
# однолітерні слова (для «Z написав» → «Я написав»)
ONE = {"en": set("ai"), "uk": set("яійвуоза"), "ru": set("яавикосу")}
VOWELS = {"en": set("aeiouy"), "uk": set("аеєиіїоуюя"), "ru": set("аеёиоуыэюя")}

COMMON = {   # запасний варіант: найчастіші буквосполучення (коли немає words_*.txt)
    "en": set("""th he in er an re on at en nd ti es or te of ed is it al ar st to nt ng se ha as ou io le ve
co me de hi ri ro ic ne ea ra ce li ch ll be ma si om ur ca el ta la ns di fo ho pe ec pr no ct us ac ot
il tr ly nc et ut ss so rs un lo wa ge ie wh ee wi em ad ol rt po we na ul ni ts mo ow pa im mi ai sh ir
su id os iv ia am fi ci vi pl ig tu ev ld ry mp fe bl ab gh ty op wo sa ay ex ke fr oo av ag if ap gr od
bo sp rd do uc bu ei ov by rm ep ys ft ck pt gu ub ib ph sc sk sm sw tw wr lk lm lp lt nk nn ws wn yo ye
ya ob ok ak ik ix ox ux iz oz ds gs ms ps rn rp rb rk rl rf rg rc rv bs""".split()),
    "ru": set("""ст но то на ен ов ни ра во ко по ро пр ре ор ос ол ал ел ер ан ат ет ит ри ть ог го ск ва ли ом ле
от ны ие ой ий ем ых ка ль ик ве ив да де му не ну ня ед ла ло лу ма ми мо об од ож оп ох па пе пи пу са
св се си сл см со сп ср су ся та те ти ту ты уч ущ хо чи че чт шн ще эт юс яв ят ящ щи ьк ьн ьс ьм юч
ця ац ач аш ащ ай аз ад аж ам ап ар ас ах ба бе би бл бр бо вл вн вр вд гл гр дж дл ея жа же жу зб зв
зд зк зм зр зу из ич иш ию ищ кв кл ки кн мб мл мн мс мч нс нт нц нч нш нь ню нй оз оя ощ оч ош пл
пн пт пя рв рд рж рз рк рл рн рт рц рч рш рь ря рю ую ия аг га нд""".split()),
    "uk": set("""на по ро ст ов ен ни пр ра ко то ер ос ан ва ре ор та ий ть не ій ат ом ка ід ал ли ол ук ін ої
ля ку ну ти ся ув го ою ем іс ле св др ак бу бо ве ви ві вс ги да де дн до ду дя еп ес ет жи за зн зо ик
ил им ин ир іл ім ір іт ія кі кр кт ла лю ма ме ми мо му нн нь об од ок он оп от па пе пи пі пу рі ру ря
са се си ск сл см сн со сп су те ті тр ту тя уд ул ум ун ур ус хо ць чи ши ще юч ют ює ян ят що сь ьо
ьк ьн ьс ьм ьш ця це ці цю ац ач аш ащ аю ає ай аз ад аж ам ап ас ах ба бе би бі бл бр вл вн вр вд гл
гр дж ді дл ел ея жа же жу зб зв зд зк зм зр зу ив із ич иш ию їх ії їм їн кв кл ки кн мб мл мн мс мч
нс нт нц нч нш ню ня нє ів оз оя ощ оч ош пл пн пт пя рв рд рж рз рк рл рн рт рц рч рш рь рє рю ує
ую ію ри ци ди зи аг га нд""".split()),
}

# Найчастіші слова з 2–3 літер (для слів коротших за MIN_LETTERS).
SHORT = {
    "en": set("""the and for you are not but was one can how why who all any get has had his her him its our out
now new see say use yes too two did let may off own put she way ok is it to of in on at as an be by do go he
if me my no or so up us we am hi""".split()),
    "ru": set("""на по за из от до не ни да но же бы ли что как так это все вот мы вы ты он ее её они его для
при без над под про или уже еще ещё там тут где кто чем нет был она оно мой наш ваш два тоже""".split()),
    "uk": set("""на по за до від не ні та що як це ми ви ти він ще бо чи ну ой ах де їх її їм при без для над під
про між усе все всі цей той ця так там тут ось уже мій наш ваш хто""".split()),
}


MASK64 = (1 << 64) - 1


def _h(text):
    return hash(text) & MASK64


class HashSet:
    """Компактна множина рядків: відсортований масив 64-бітних хешів (8 байт на слово замість ~100)."""
    __slots__ = ("a",)

    def __init__(self, hashes=()):
        self.a = array("Q", sorted(set(hashes)))

    def __contains__(self, text):
        h = _h(text)
        i = bisect.bisect_left(self.a, h)
        return i < len(self.a) and self.a[i] == h

    def __len__(self):
        return len(self.a)


def _load_words(lang):
    """words_<lang>.txt: «слово» або «слово кількість» (як у FrequencyWords). Порядок = частота.
    Повертає (словник найчастіших слів зі своїм рангом, компактну множину всіх прочитаних слів)."""
    top, hashes = {}, []
    try:
        with open(os.path.join(HERE, f"words_{lang}.txt"), encoding="utf-8-sig") as f:
            n = 0
            for line in f:
                parts = line.split(None, 1)
                if not parts:
                    continue
                w = parts[0].lower()
                if not w.isalpha():
                    continue
                n += 1
                if n > WORDS_MAX:
                    break
                if len(top) < WORDS_TOP:
                    top.setdefault(w, len(top))
                hashes.append(_h(w))
    except OSError:
        pass
    return top, HashSet(hashes)


def _build_trigrams(words):
    """Множина «правдоподібних» триграм (з маркерами початку/кінця) зі словника."""
    if len(words) < 1000:
        return set()
    cnt = Counter()
    for w in words:
        if w.isalpha():
            p = "^" + w + "$"
            for i in range(len(p) - 2):
                cnt[p[i:i + 3]] += 1
    return {t for t, c in cnt.items() if c >= 3}


def _add_prefixes(table, word):
    if word.isalpha() and len(word) >= 3:
        for n in range(3, min(len(word), 6) + 1):
            p = word[:n]
            table[p] = table.get(p, 0) + 1


def _build_prefixes(words):
    """Скільки слів починається з кожного початку довжиною 3–6 літер (для режиму «на льоту»)."""
    table = {}
    for w in words:
        _add_prefixes(table, w)
    return table


WORDS, WORDSET = {}, {}
for _lang in KLID:
    WORDS[_lang], WORDSET[_lang] = _load_words(_lang)
TRI = {lang: _build_trigrams(WORDS[lang]) for lang in KLID}
PFX = {lang: _build_prefixes(WORDS[lang]) for lang in KLID}
NGRAM, TYPO, HUN = {}, {}, {}      # заповнюються у фоні (build_models)
LEARNED = {lang: {} for lang in KLID}

# ───────────────────────────── WinAPI ───────────────────────────────────
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32", use_last_error=True)
VP = ctypes.c_void_p

HOOKPROC = ctypes.WINFUNCTYPE(wt.LPARAM, ctypes.c_int, wt.WPARAM, wt.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(wt.LPARAM, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class GUID(ctypes.Structure):
    _fields_ = [("d1", wt.DWORD), ("d2", wt.WORD), ("d3", wt.WORD), ("d4", ctypes.c_ubyte * 8)]


def make_guid(text):
    u = uuid.UUID(text)
    g = GUID()
    g.d1, g.d2, g.d3 = u.time_low, u.time_mid, u.time_hi_version
    for i, b in enumerate(u.bytes[8:]):
        g.d4[i] = b
    return g


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("flags", wt.DWORD), ("hwndActive", wt.HWND),
                ("hwndFocus", wt.HWND), ("hwndCapture", wt.HWND), ("hwndMenuOwner", wt.HWND),
                ("hwndMoveSize", wt.HWND), ("hwndCaret", wt.HWND), ("rcCaret", wt.RECT)]


user32.ToUnicodeEx.argtypes = [wt.UINT, wt.UINT, VP, wt.LPWSTR, ctypes.c_int, wt.UINT, VP]
user32.ToUnicodeEx.restype = ctypes.c_int
user32.LoadKeyboardLayoutW.argtypes = [wt.LPCWSTR, wt.UINT]
user32.LoadKeyboardLayoutW.restype = VP
user32.GetKeyboardLayout.argtypes = [wt.DWORD]
user32.GetKeyboardLayout.restype = VP
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetGUIThreadInfo.argtypes = [wt.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.GetGUIThreadInfo.restype = wt.BOOL
user32.FindWindowExW.argtypes = [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowExW.restype = wt.HWND
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, VP]
user32.PostThreadMessageW.argtypes = [wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetKeyState.argtypes = [ctypes.c_int]
user32.GetKeyState.restype = ctypes.c_short
user32.SendInput.argtypes = [wt.UINT, VP, ctypes.c_int]
user32.CallNextHookEx.argtypes = [VP, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = wt.LPARAM
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, VP, wt.DWORD]
user32.SetWindowsHookExW.restype = VP
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.DefWindowProcW.restype = wt.LPARAM
user32.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]
user32.CreatePopupMenu.restype = VP
user32.AppendMenuW.argtypes = [VP, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
user32.TrackPopupMenu.argtypes = [VP, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND, VP]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.DestroyMenu.argtypes = [VP]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.CreateIconIndirect.argtypes = [VP]
user32.CreateIconIndirect.restype = VP
gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wt.UINT, wt.UINT, VP]
gdi32.CreateBitmap.restype = VP
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = VP
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = VP
kernel32.QueryFullProcessImageNameW.argtypes = [VP, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [VP]
kernel32.CreateMutexW.argtypes = [VP, wt.BOOL, wt.LPCWSTR]
kernel32.CreateMutexW.restype = VP
ole32.CoInitializeEx.argtypes = [VP, wt.DWORD]
ole32.CoInitializeEx.restype = ctypes.c_long
ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), VP, wt.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(VP)]
ole32.CoCreateInstance.restype = ctypes.c_long

WH_KEYBOARD_LL, WH_MOUSE_LL, WM_INPUTLANGCHANGEREQUEST = 13, 14, 0x50
KEYEVENTF_EXTENDED, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x1, 0x2, 0x4
LLKHF_EXTENDED, LLKHF_INJECTED, LLKHF_UP = 0x01, 0x10, 0x80
MARK = 0x4C53574B
MAIN_TID = kernel32.GetCurrentThreadId()


class KBDLL(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


HKL = {lang: user32.LoadKeyboardLayoutW(klid, 0) for lang, klid in KLID.items()}
Key = namedtuple("Key", "vk sc shift caps ch lang")
# bs — скільки Backspace, text — що надрукувати, tgt — на яку розкладку перемкнути,
# sep — клавіша-роздільник (0x20/0x0D/0x09 або 0); orig/orig_lang/orig_core — для скасування
Plan = namedtuple("Plan", "bs text tgt sep orig orig_lang orig_core")

MODS = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x14, 0x5B, 0x5C, 0x90, 0x91}
NAV = {0x0D, 0x09, 0x1B, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}
SEP_SCAN = {0x20: 0x39, 0x0D: 0x1C, 0x09: 0x0F}


DEBUG = "--debug" in sys.argv


def dbg(*args):
    """Діагностика: працює лише з ключем --debug і друкує в консоль (на диск нічого не пишеться)."""
    if DEBUG:
        try:
            print(time.strftime("%H:%M:%S"), *args, flush=True)
        except Exception:
            pass


def lang_of(hkl):
    return PRIMARY.get((hkl or 0) & 0x3FF)


def vk_to_char(vk, sc, shift, caps, hkl):
    """Який символ дає ця фізична клавіша в заданій розкладці."""
    st = (ctypes.c_ubyte * 256)()
    if shift:
        st[0x10] = 0x80
    if caps:
        st[0x14] = 0x01
    out = ctypes.create_unicode_buffer(8)
    n = user32.ToUnicodeEx(vk, sc, st, out, 8, 4, hkl)   # прапор 4: не змінювати стан «мертвих» клавіш
    return out.value[:n] if n == 1 else ""


def focus_hwnd():
    """Вікно, яке реально приймає введення (важливо для UWP/XAML-програм, як Блокнот у Win11)."""
    fg = user32.GetForegroundWindow()
    if not fg:
        return 0
    core = user32.FindWindowExW(fg, None, "Windows.UI.Core.CoreWindow", None)
    if core:
        return core
    gi = GUITHREADINFO()
    gi.cbSize = ctypes.sizeof(gi)
    if user32.GetGUIThreadInfo(0, ctypes.byref(gi)) and gi.hwndFocus:
        return gi.hwndFocus
    return fg


def layout_of(hwnd):
    return user32.GetKeyboardLayout(user32.GetWindowThreadProcessId(hwnd, None))


def exe_of(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return ""
    try:
        buf, size = ctypes.create_unicode_buffer(520), wt.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def is_password_field(hwnd):
    """Класичне поле пароля (Edit з ES_PASSWORD). Сучасні/браузерні поля розпізнати неможливо."""
    try:
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, buf, 64)
        return buf.value.lower().startswith("edit") and bool(user32.GetWindowLongW(hwnd, -16) & 0x20)
    except Exception:
        return False


# ───────────────────────────── Чорний список ────────────────────────────
_bl = {"mtime": object(), "names": set(EXCLUDED_EXE)}
_exe_cache = {"hwnd": 0, "t": 0.0, "exe": ""}


def excluded(exe):
    """Перечитує blacklist.txt лише коли файл змінився."""
    try:
        mtime = os.path.getmtime(BL_PATH)
    except OSError:
        mtime = None
    if mtime != _bl["mtime"]:
        names = set(EXCLUDED_EXE)
        if mtime is not None:
            try:
                with open(BL_PATH, encoding="utf-8-sig") as f:
                    for line in f:
                        line = line.split("#", 1)[0].strip().lower()
                        if line:
                            names.add(line if line.endswith(".exe") else line + ".exe")
            except OSError:
                pass
        _bl["mtime"], _bl["names"] = mtime, names
    return exe in _bl["names"]


def app_excluded(hwnd):
    """Чи у чорному списку програма вікна hwnd (ім'я exe кешується на 2 с)."""
    now = time.time()
    if _exe_cache["hwnd"] != hwnd or now - _exe_cache["t"] > 2.0:
        _exe_cache.update(hwnd=hwnd, t=now, exe=exe_of(hwnd))
    return excluded(_exe_cache["exe"])


def open_blacklist():
    if not os.path.exists(BL_PATH):
        try:
            with open(BL_PATH, "w", encoding="utf-8") as f:
                f.write(BL_TEMPLATE)
        except OSError:
            return
    os.startfile(BL_PATH)


# ───────────────────────────── Автозапуск ───────────────────────────────
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "LayoutSwitcher"


def _launch_cmd():
    if FROZEN:
        return f'"{sys.executable}"'
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pyw if os.path.exists(pyw) else sys.executable}" "{os.path.abspath(__file__)}"'


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, RUN_NAME)[0] == _launch_cmd()
    except OSError:
        return False


def set_autostart(on):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, _launch_cmd())
            else:
                winreg.DeleteValue(k, RUN_NAME)
    except OSError:
        pass


# ───────────────── Перевірка правопису Windows (локально, offline) ──────
# Windows Spell Checking API (Win8+): ISpellCheckerFactory → ISpellChecker.Check().
# Слово правильне, якщо IEnumSpellingError.Next повертає S_FALSE (помилок немає).
# Обʼєкти COM створюються окремо в кожному потоці; будь-яка помилка → просто без цього словника.
CLSID_SPELL = make_guid("7AB36653-1796-484B-BDFA-E74F1DB7C1DC")
IID_SPELL_FACTORY = make_guid("8E018A9D-2415-4677-BF08-794EA61F94BB")
_tls = threading.local()
_spell_cache = {}


def _vcall(obj, index, argtypes, *args):
    vtbl = ctypes.cast(ctypes.cast(obj, ctypes.POINTER(VP))[0], ctypes.POINTER(VP))
    proto = ctypes.WINFUNCTYPE(ctypes.c_long, VP, *argtypes)
    return proto(vtbl[index])(obj, *args)


def spell_checker(lang):
    """ISpellChecker для мови або None. Перший виклик у потоці створює фабрику."""
    if not USE_WINDOWS_SPELLCHECK:
        return None
    if not hasattr(_tls, "checkers"):
        _tls.checkers, _tls.factory, _tls.slow = {}, None, 0
        try:
            ole32.CoInitializeEx(None, 0)                       # COINIT_MULTITHREADED
            f = VP()
            hr = ole32.CoCreateInstance(ctypes.byref(CLSID_SPELL), None, 0x17,
                                        ctypes.byref(IID_SPELL_FACTORY), ctypes.byref(f))
            if hr == 0 and f.value:
                _tls.factory = f.value
        except Exception:
            _tls.factory = None
    if _tls.factory is None or _tls.slow >= 3:
        return None
    if lang not in _tls.checkers:
        chk = None
        try:
            ok = wt.BOOL()
            hr = _vcall(_tls.factory, 4, [wt.LPCWSTR, ctypes.POINTER(wt.BOOL)], TAGS[lang], ctypes.byref(ok))
            if hr == 0 and ok.value:
                out = VP()
                hr = _vcall(_tls.factory, 5, [wt.LPCWSTR, ctypes.POINTER(VP)], TAGS[lang], ctypes.byref(out))
                if hr == 0 and out.value:
                    chk = out.value
        except Exception:
            chk = None
        _tls.checkers[lang] = chk
    return _tls.checkers[lang]


def _spell_raw(lang, word):
    chk = spell_checker(lang)
    if chk is None:
        return None
    t0 = time.perf_counter()
    try:
        enum = VP()
        if _vcall(chk, 4, [wt.LPCWSTR, ctypes.POINTER(VP)], word, ctypes.byref(enum)) != 0 or not enum.value:
            return None
        err = VP()
        hr = _vcall(enum.value, 3, [ctypes.POINTER(VP)], ctypes.byref(err))
        _vcall(enum.value, 2, [])                               # Release
        if hr == 0 and err.value:
            _vcall(err.value, 2, [])
        return hr == 1                                          # S_FALSE: помилок немає
    except Exception:
        return None
    finally:
        if time.perf_counter() - t0 > SPELL_SLOW:
            _tls.slow += 1


def spell_valid(lang, word, capitalized=False):
    """True/False — слово є/немає у словнику Windows; None — словник недоступний."""
    key = (lang, word)
    if key in _spell_cache:
        res = _spell_cache[key]
    else:
        res = _spell_raw(lang, word)
        if res is False and capitalized:                        # власні назви: «Київ», «Python»
            res = _spell_raw(lang, word.capitalize()) or False
        if res is not None and len(_spell_cache) < 100000:
            _spell_cache[key] = res
    return res


def spell_warmup():
    """Завантажуємо словники заздалегідь, щоб перший виклик не гальмував хук."""
    for lang, w in (("en", "test"), ("uk", "тест"), ("ru", "тест")):
        spell_valid(lang, w)


# ───────────────────────────── Збережені перемикачі ─────────────────────
SET_KEY = r"Software\LayoutSwitcher"


def load_settings():
    for name, attr in (("Flag", "flag"), ("Learn", "learn"), ("Fly", "fly")):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SET_KEY) as k:
                setattr(S, attr, bool(winreg.QueryValueEx(k, name)[0]))
        except OSError:
            pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SET_KEY) as k:
            v = winreg.QueryValueEx(k, "FlyMin")[0]
            if v in (3, 4, 5):
                S.fly_min = v
    except OSError:
        pass


def save_setting(name, value):
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SET_KEY) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, int(value))
    except OSError:
        pass


# ───────────────────────────── Самонавчання ─────────────────────────────
LEARN_LOCK = threading.Lock()
LEARN_PATH = None
LEARN_COUNTS = Counter()       # лише в пам'яті


def _pick_learn_path():
    for d in (HERE, os.path.join(os.environ.get("APPDATA", HERE), "LayoutSwitcher")):
        try:
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, "learned.txt")
            with open(p, "a", encoding="utf-8"):
                pass
            return p
        except OSError:
            continue
    return None


def load_learned():
    global LEARN_PATH
    LEARN_PATH = _pick_learn_path()
    if not LEARN_PATH:
        return
    try:
        with open(LEARN_PATH, encoding="utf-8-sig") as f:
            for line in f:
                lang, _, word = line.rstrip("\n").partition("\t")
                if lang in LEARNED and word:
                    LEARNED[lang][word.lower()] = 1
                    _add_prefixes(PFX[lang], word.lower())
    except OSError:
        pass


def learned_total():
    return sum(len(d) for d in LEARNED.values())


def _persist(lang, word):
    with LEARN_LOCK:
        if LEARN_PATH:
            try:
                with open(LEARN_PATH, "a", encoding="utf-8") as f:
                    f.write(f"{lang}\t{word}\n")
            except OSError:
                pass


def learn(lang, word):
    """Запам'ятати слово як правильне для мови (з файлом learned.txt)."""
    word = word.lower()
    if not (3 <= len(word) <= 24) or not word.isalpha() or word in LEARNED[lang] or learned_total() >= LEARN_MAX:
        return
    LEARNED[lang][word] = 1
    _add_prefixes(PFX[lang], word)
    dbg("вивчено:", lang, word)
    threading.Thread(target=_persist, args=(lang, word), daemon=True).start()


def forget_all():
    for d in LEARNED.values():
        d.clear()
    LEARN_COUNTS.clear()
    with LEARN_LOCK:
        if LEARN_PATH:
            try:
                with open(LEARN_PATH, "w", encoding="utf-8"):
                    pass
            except OSError:
                pass


def maybe_learn(lang, word):
    """Ручна корекція: вчимо слово, лише якщо воно схоже на справжнє (не сміття від перебору розкладок)."""
    letters = word.lower()
    if not letters.isalpha() or len(letters) < 3 or score(letters, lang) == 1.0:
        return                                        # не слово або вже відоме словникам
    # Дивимося на «сиру» правдоподібність, а не на score: коли словник Windows каже «такого слова
    # немає» (сленг, нова лексика, імена), score навмисно ≤ 0.2, і ручну корекцію ніколи б не вивчили.
    if model(letters, lang) >= 0.3:
        learn(lang, letters)


def observe(keys, foc):
    """Слово набране й не виправлялось: якщо його немає в словниках — рахуємо повтори."""
    if not S.learn or not keys or len({k.lang for k in keys}) > 1:
        return
    lang = keys[0].lang
    raw = "".join(k.ch for k in keys)
    text = raw.strip("".join({c for c in raw if not c.isalpha()}))
    if not (3 <= len(text) <= 24) or not text.isalpha():
        return
    if any(c.isupper() for c in text[1:]) and not text.isupper():
        return                                                   # CamelCase та ідентифікатори
    word = text.lower()
    if score(word, lang) == 1.0 or app_excluded(foc):
        return
    LEARN_COUNTS[(lang, word)] += 1
    if LEARN_COUNTS[(lang, word)] >= LEARN_THRESHOLD:
        del LEARN_COUNTS[(lang, word)]
        learn(lang, word)


# ───────────────────────────── Мовна модель (n-грами) ───────────────────
class NGram:
    """Символьна n-грамна модель зі згладжуванням Віттена–Белла. Оцінює, наскільки рядок схожий на слово
    мови: рахує середню «здивованість» H (нат/символ) і калібрує поріг на словах, яких модель не бачила."""

    def __init__(self, words, order=NGRAM_ORDER):
        self.n = order
        pad = "^" * (order - 1)
        counts, held = Counter(), []
        for i, w in enumerate(words):
            if i % 10 == 9:
                held.append(w)                       # кожне 10-те слово не вчимо: на ньому калібруємо пороги
                continue
            s_ = pad + w + "$"
            counts.update([s_[j - k:j + 1] for j in range(order - 1, len(s_)) for k in range(order)])
            if i % 400 == 0:
                time.sleep(0)                        # даємо дорогу хуку клавіатури
        self.tot, self.typ = {}, {}
        for key, c in counts.items():
            ctx = key[:-1]
            self.tot[ctx] = self.tot.get(ctx, 0) + c
            self.typ[ctx] = self.typ.get(ctx, 0) + 1
        self.counts = counts
        self.uni = 1.0 / (sum(1 for key in counts if len(key) == 1) + 1)
        hs = sorted(self.h(w) for w in held[:2500]) or [3.0]
        self.h0 = hs[int(len(hs) * 0.85)]            # «межа» нормального слова: 85-й перцентиль
        med, p95 = hs[len(hs) // 2], hs[min(len(hs) - 1, int(len(hs) * 0.95))]
        self.t = max(0.15, (p95 - med) / 2.5)

    def h(self, word):
        """Середня здивованість моделі на символ слова (менше = більше схоже на слово)."""
        n = self.n
        s_ = "^" * (n - 1) + word + "$"
        total = 0.0
        for j in range(n - 1, len(s_)):
            c = s_[j]
            p = self.uni
            for k in range(n):
                ctx = s_[j - k:j]
                t = self.tot.get(ctx)
                if not t:
                    break
                lam = t / (t + self.typ[ctx])
                p = lam * (self.counts.get(ctx + c, 0) / t) + (1.0 - lam) * p
            total += math.log(p)
        return -total / (len(s_) - n + 1)

    def plausibility(self, word):
        x = (self.h(word) - self.h0) / self.t
        return 0.0 if x > 30 else min(0.85, 1.0 / (1.0 + math.exp(x)))


# ───────────────────────────── Слова з опечатками ───────────────────────
def _build_typo(lang):
    """Індекс «слово без однієї літери» (хеші) для найчастіших слів: так шукають слова на відстані 1."""
    dels = []
    for i, w in enumerate(WORDS[lang]):
        if i >= TYPO_WORDS:
            break
        if 6 <= len(w) <= 11:
            for j in range(len(w)):
                dels.append(_h(w[:j] + w[j + 1:]))
        if i % 3000 == 0:
            time.sleep(0)
    return HashSet(dels)


def near_word(lang, w):
    """Чи відрізняється w від слова зі словника однією літерою (пропуск, зайва або заміна)?"""
    d = TYPO.get(lang)
    if d is None or not (6 <= len(w) <= 11):
        return False
    if w in d:                                        # у w пропущена літера
        return True
    ws = WORDSET[lang]
    for i in range(len(w)):
        x = w[:i] + w[i + 1:]
        if x in ws or x in d:                         # у w зайва літера або заміна
            return True
    return False


# ───────────────────────────── Словники Hunspell ────────────────────────
HUN_NAMES = {"en": "en_US", "uk": "uk_UA", "ru": "ru_RU"}


class Hunspell:
    """Мінімальний рушій Hunspell: .dic зі стовбурами + правила афіксів .aff (суфікси, префікси,
    їх поєднання). Слова перевіряються відсіканням афіксів, без розгортання всіх форм у пам'ять."""

    def __init__(self, aff_path, dic_path):
        self.sfx, self.pfx, self.words, self.cross, self._fc = {}, {}, {}, {}, {}
        self.flagmode = "char"
        raw = open(aff_path, "rb").read()
        enc = "utf-8"
        m = re.search(rb"^SET\s+(\S+)", raw, re.M)
        if m:
            name = m.group(1).decode("ascii", "ignore").lower().replace("microsoft-", "cp")
            try:
                enc = codecs.lookup(name).name
            except LookupError:
                enc = "utf-8"
        self._parse_aff(raw.decode(enc, "replace"))
        self._parse_dic(open(dic_path, "rb").read().decode(enc, "replace"))
        self.maxs = max((len(k) for k in self.sfx), default=0)
        self.maxp = max((len(k) for k in self.pfx), default=0)

    def _parse_aff(self, text):
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            p = line.split()
            key = p[0]
            if key == "FLAG" and len(p) > 1:
                self.flagmode = p[1].lower()
            elif key in ("SFX", "PFX") and len(p) >= 4:
                if len(p) == 4 and p[2] in ("Y", "N") and p[3].isdigit():
                    self.cross[(key, p[1])] = (p[2] == "Y")          # заголовок групи правил
                elif len(p) >= 5:
                    flag, strip, add, cond = p[1], p[2], p[3].split("/", 1)[0], p[4]
                    strip = "" if strip == "0" else strip
                    add = "" if add == "0" else add
                    rx = None
                    if cond != ".":
                        try:
                            rx = re.compile(cond + "$" if key == "SFX" else "^" + cond)
                        except re.error:
                            continue
                    table = self.sfx if key == "SFX" else self.pfx
                    table.setdefault(add, []).append((flag, strip, rx, self.cross.get((key, flag), True)))

    def _parse_dic(self, text):
        lines = text.splitlines()
        for line in lines[1:] if lines and lines[0].strip().isdigit() else lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            tok = line.split(None, 1)[0]
            w, _, fl = tok.partition("/")
            if w:
                old = self.words.get(w)
                self.words[w] = fl if old is None else old + ("," if self.flagmode == "num" else "") + fl

    def _flags(self, f):
        fs = self._fc.get(f)
        if fs is None:
            if self.flagmode == "long":
                fs = {f[i:i + 2] for i in range(0, len(f), 2)}
            elif self.flagmode == "num":
                fs = set(f.split(","))
            else:
                fs = set(f)
            self._fc[f] = fs
        return fs

    def _check(self, w):
        words, n = self.words, len(w)
        if w in words:
            return True
        for L in range(0, min(self.maxs, n - 1) + 1):                     # суфікс довжиною L
            for flag, strip, rx, _c in self.sfx.get(w[n - L:] if L else "", ()):
                stem = w[:n - L] + strip
                if stem and (rx is None or rx.search(stem)):
                    f = words.get(stem)
                    if f is not None and flag in self._flags(f):
                        return True
        for L in range(1, min(self.maxp, n - 1) + 1):                     # префікс довжиною L
            for pflag, strip, rx, cross in self.pfx.get(w[:L], ()):
                stem = strip + w[L:]
                if not stem or (rx is not None and not rx.search(stem)):
                    continue
                f = words.get(stem)
                if f is not None and pflag in self._flags(f):
                    return True
                if cross:                                                  # префікс + суфікс разом
                    m = len(stem)
                    for L2 in range(0, min(self.maxs, m - 1) + 1):
                        for sflag, sstrip, srx, scross in self.sfx.get(stem[m - L2:] if L2 else "", ()):
                            stem2 = stem[:m - L2] + sstrip
                            if scross and stem2 and (srx is None or srx.search(stem2)):
                                f2 = words.get(stem2)
                                if f2 is not None:
                                    fs = self._flags(f2)
                                    if pflag in fs and sflag in fs:
                                        return True
        return False

    def valid(self, w):
        return (self._check(w) or self._check(w.lower())
                or (w[:1].upper() + w[1:] != w and self._check(w[:1].upper() + w[1:])))


_hun_slow = [0]


def load_hunspell():
    """Шукає uk_UA/ru_RU/en_US (.aff + .dic) поруч із програмою або в папці dictionaries."""
    for lang, name in HUN_NAMES.items():
        for d in (os.path.join(HERE, "dictionaries"), HERE):
            aff, dic = os.path.join(d, name + ".aff"), os.path.join(d, name + ".dic")
            if os.path.exists(aff) and os.path.exists(dic):
                try:
                    HUN[lang] = Hunspell(aff, dic)
                except Exception as e:
                    dbg("Hunspell", name, "не завантажено:", e)
                break


def hun_valid(lang, word, cap=False):
    h = HUN.get(lang)
    if h is None or _hun_slow[0] >= 3:
        return None
    t0 = time.perf_counter()
    try:
        res = h.valid(word)
    except Exception:
        return None
    if time.perf_counter() - t0 > HUN_SLOW:
        _hun_slow[0] += 1
    return res


_dict_cache = {}


def dict_valid(lang, letters, cap=False):
    """True/False — слово є/немає у словниках (Hunspell, Windows); None — жодного словника немає."""
    key = (lang, letters)
    if key in _dict_cache:
        return _dict_cache[key]
    results = [hun_valid(lang, letters), spell_valid(lang, letters, cap)]
    if any(r is True for r in results):
        res = True
    elif any(r is False for r in results):
        res = False
    else:
        return None                                   # не кешуємо: словники можуть ще вантажитись
    if len(_dict_cache) < 200000:
        _dict_cache[key] = res
    return res


def build_models():
    """Важкі побудови у фоні, щоб не затримувати запуск: n-грамні моделі, індекс опечаток, словники Hunspell."""
    try:
        sys.setswitchinterval(0.001)                  # хук клавіатури не повинен чекати на фоновий потік
    except Exception:
        pass
    for lang in KLID:
        try:
            if len(WORDS[lang]) >= 1000:
                NGRAM[lang] = NGram(list(WORDS[lang])[:MODEL_WORDS])
                TYPO[lang] = _build_typo(lang)
        except Exception as e:
            dbg("модель", lang, "не побудована:", e)
    try:
        load_hunspell()
    except Exception as e:
        dbg("Hunspell:", e)
    _dict_cache.clear()
    dbg("моделі готові: n-грами", list(NGRAM), "опечатки", list(TYPO), "hunspell", list(HUN))


# ───────────────────────────── Навчання зі своїх документів ─────────────
DOC_EXT = {".txt", ".md", ".csv", ".log", ".srt", ".html", ".htm", ".xml", ".fb2", ".rtf", ".docx", ".odt"}
DOC_LIMITS = {"files": 5000, "bytes": 400 * 1024 * 1024, "seconds": 180, "file_bytes": 25 * 1024 * 1024}
TOKEN_RE = re.compile(r"[^\W\d_]{3,}")


def _read_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".docx", ".odt"):
        member = "word/document.xml" if ext == ".docx" else "content.xml"
        with zipfile.ZipFile(path) as z:
            if z.getinfo(member).file_size > 40 * 1024 * 1024:
                return ""
            xml = z.read(member).decode("utf-8", "replace")
        xml = re.sub(r"</w:p>|<w:br\s*/?>|<w:tab\s*/?>|</text:p>|</text:h>|<text:s\s*/?>|<text:tab\s*/?>", "\n", xml)
        return html.unescape(re.sub(r"<[^>]+>", "", xml))     # без пробілу: слово може бути розбите на «run»-и
    with open(path, "rb") as f:
        data = f.read(DOC_LIMITS["file_bytes"])
    for enc in ("utf-8-sig", "cp1251"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", "replace")
    if ext in (".html", ".htm", ".xml", ".fb2"):
        text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    elif ext == ".rtf":
        text = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1251", "replace"), text)
        text = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), text)
        text = re.sub(r"\\[a-zA-Z]+-?\d* ?|[{}]", " ", text)
    return text


def _token_lang(t, cyr):
    if t.isascii():
        return "en"
    if all("\u0400" <= c <= "\u04ff" for c in t):
        if any(c in UK_ONLY for c in t):
            return "uk"
        if any(c in RU_ONLY for c in t):
            return "ru"
        return cyr                                    # неоднозначне слово: мова документа
    return None


def scan_documents(folder):
    """Рахує слова у ваших документах. Повертає ({мова: Counter}, кількість файлів)."""
    counts = {l: Counter() for l in KLID}
    t0, nfiles, nbytes = time.time(), 0, 0
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith((".", "$"))]
        for name in names:
            if os.path.splitext(name)[1].lower() not in DOC_EXT:
                continue
            if (nfiles >= DOC_LIMITS["files"] or nbytes >= DOC_LIMITS["bytes"]
                    or time.time() - t0 > DOC_LIMITS["seconds"]):
                return counts, nfiles
            path = os.path.join(root, name)
            try:
                size = os.path.getsize(path)
                text = _read_text(path).lower()
            except (OSError, zipfile.BadZipFile, KeyError, ValueError):
                continue
            nfiles += 1
            nbytes += size
            toks = [t for t in TOKEN_RE.findall(text) if len(t) <= 24]
            uniq = set(toks)
            uk = sum(1 for t in uniq if any(c in UK_ONLY for c in t))
            ru = sum(1 for t in uniq if any(c in RU_ONLY for c in t))
            cyr = "uk" if uk > ru else ("ru" if ru > uk else S.cyr)
            for t, c in Counter(toks).items():
                lang = _token_lang(t, cyr)
                if lang:
                    counts[lang][t] += c
            time.sleep(0)
    return counts, nfiles


def learn_many(lang, words):
    """Додає багато слів за раз (один запис у learned.txt)."""
    new = []
    for w in words:
        if learned_total() >= LEARN_MAX:
            break
        if w not in LEARNED[lang] and 3 <= len(w) <= 24 and w.isalpha():
            LEARNED[lang][w] = 1
            _add_prefixes(PFX[lang], w)
            new.append(w)
    if new and LEARN_PATH:
        with LEARN_LOCK:
            try:
                with open(LEARN_PATH, "a", encoding="utf-8") as f:
                    f.write("".join(f"{lang}\t{w}\n" for w in new))
            except OSError:
                pass
    return len(new)


def learn_from_counts(counts):
    """З порахованих слів вчимо ті, що зустрілись >= DOC_MIN_COUNT разів і яких ще не знають словники."""
    added, budget = {}, DOC_MAX_NEW
    for lang, c in counts.items():
        fresh = []
        for w, n in c.most_common(60000):
            if n < DOC_MIN_COUNT or len(fresh) >= budget:
                break
            if 3 <= len(w) <= 24 and score(w, lang) != 1.0:
                fresh.append(w)
        added[lang] = learn_many(lang, fresh)
        budget -= added[lang]
    return added


def msgbox(text, title="LayoutSwitcher"):
    user32.MessageBoxW(None, text, title, 0x40 | 0x10000 | 0x40000)


def pick_folder():
    """Вікно вибору папки. '' — скасовано; None — вікно недоступне (немає tkinter)."""
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        path = filedialog.askdirectory(title="Оберіть папку зі своїми документами", mustexist=True)
        root.destroy()
        return path or ""
    except Exception:
        return None


def learn_from_documents():
    folder = pick_folder()
    if folder is None:
        msgbox("Не вдалося відкрити вікно вибору папки (немає tkinter).")
        return
    if not folder:
        return
    try:
        counts, nfiles = scan_documents(folder)
        added = learn_from_counts(counts)
    except Exception as e:
        msgbox(f"Не вдалося завершити навчання: {e}")
        return
    msgbox(f"Проскановано файлів: {nfiles}.\n"
           f"Нових слів: українських {added.get('uk', 0)}, російських {added.get('ru', 0)}, "
           f"англійських {added.get('en', 0)}.\n\n"
           f"Слова записано у {LEARN_PATH or 'learned.txt'}. Помилкові видаліть звідти й перезапустіть програму.")


# ───────────────────────────── Оцінка слова ─────────────────────────────
def model(letters, lang):
    """Правдоподібність невідомого слова 0..0.85: n-грамна модель, інакше триграми, інакше пари літер."""
    if not any(c in VOWELS[lang] for c in letters):
        return 0.0
    ng = NGRAM.get(lang)
    if ng is not None:
        return ng.plausibility(letters)
    tri = TRI[lang]
    if tri:
        p = "^" + letters + "$"
        grams = [p[i:i + 3] for i in range(len(p) - 2)]
        cov = sum(g in tri for g in grams) / len(grams)
        return min(0.85, 0.9 * cov * cov)
    pairs = [letters[i:i + 2] for i in range(len(letters) - 1)]
    return sum(p in COMMON[lang] for p in pairs) / len(pairs)


def score(text, lang):
    """0..1 — наскільки текст схожий на слово мови lang; None — оцінити неможливо."""
    letters = "".join(c for c in text.lower() if c not in "'’ʼ-")
    if not letters.isalpha() or len(letters) < MIN_SHORT:
        return None
    if lang == "uk" and any(c in RU_ONLY for c in letters):
        return 0.0
    if lang == "ru" and any(c in UK_ONLY for c in letters):
        return 0.0
    if letters in LEARNED[lang]:
        return 1.0
    short = len(letters) < MIN_LETTERS
    rank = WORDS[lang].get(letters)
    if rank is not None and (not short or rank < SHORT_RANK):
        return 1.0
    if short:                                       # слова з 2–3 літер: лише за словниками
        return 1.0 if letters in SHORT[lang] else 0.0
    if letters in WORDSET[lang]:
        return 1.0
    ok = dict_valid(lang, letters, text[:1].isupper())
    if ok is True:
        return 1.0
    if near_word(lang, letters):                    # слово з однією опечаткою: «майже слово»
        return 0.7
    m = model(letters, lang)
    if ok is False:                                  # словники кажуть «такого слова немає»: не «своє» і не ціль
        return min(m, 0.2)
    return m


def convert(keys, lang):
    return [k.ch if lang == k.lang else vk_to_char(k.vk, k.sc, k.shift, k.caps, HKL[lang]) for k in keys]


def analyse(keys):
    """Для кожної мови: (оцінка, скільки клавіш зліва/справа вважати пунктуацією, ядро слова)."""
    res = {}
    n = len(keys)
    for lang in KLID:
        conv = convert(keys, lang)
        best = None
        for lead in (0, 1):
            for trail in (0, 1):
                if (lead and keys[0].ch.isalnum()) or (trail and keys[-1].ch.isalnum()):
                    continue
                if lead + trail >= n:
                    continue
                core = "".join(conv[lead:n - trail])
                s = score(core, lang)
                if s is not None and (best is None or s > best[0]):
                    best = (s, lead, trail, core)
        res[lang] = best
    return keys[0].lang, res


def ctx_bonus(lang):
    """Мова попередніх слів речення трохи підсилює свою мову (до CTX_WEIGHT)."""
    recent = list(S.ctx)[-3:]
    return CTX_WEIGHT * recent.count(lang) / len(recent) if recent else 0.0


def note_word(keys):
    """Запам'ятовуємо мову правильно набраного слова: це контекст для наступних."""
    if len({k.lang for k in keys}) > 1:
        return
    raw = "".join(k.ch for k in keys)
    core = raw.strip("".join({c for c in raw if not c.isalpha()}))
    if len(core) >= 3 and score(core, keys[0].lang) == 1.0:
        S.ctx.append(keys[0].lang)


def pick(cands):
    """Найкраща мова; кирилична мова, якою ви друкували востаннє, отримує невеликий бонус."""
    return max(cands, key=lambda l: cands[l][0] + (0.1 if l == S.cyr else 0.0))


def decide(keys, auto):
    """(мова, lead, trail, ядро) або None, якщо виправляти не треба."""
    if not keys or len({k.lang for k in keys}) > 1:
        return None
    cur, res = analyse(keys)
    cands = {l: v for l, v in res.items() if l != cur and v}
    if auto:
        if not cands:
            return None
        if res[cur]:
            cs, _, _, cur_core = res[cur]
        else:    # у поточній розкладці це не слово (є розділові знаки всередині)
            cs, cur_core = 0.0, "".join(k.ch for k in keys)
            if any(k.ch.isdigit() for k in keys):
                return None
        if len(cur_core) > 1 and any(c.isupper() for c in cur_core[1:]) and not cur_core.isupper():
            return None    # схоже на CamelCase/ідентифікатор
        if len(cur_core) < MIN_LETTERS and cur_core.isupper():
            return None    # короткі абревіатури (DS, PC, ID) не чіпаємо
        cs = min(1.0, cs + ctx_bonus(cur))                     # контекст речення
        cands = {l: (v[0] + ctx_bonus(l),) + tuple(v[1:]) for l, v in cands.items()}   # без стелі: бонус має різнити 1.0 і 1.0
        tgt = pick(cands)
        s, lead, trail, core = cands[tgt]
        if cs <= CUR_MAX and s >= ALT_MIN and s - cs >= MARGIN:
            return tgt, lead, trail, core
        return None
    if cands:
        tgt = pick(cands)
        _, lead, trail, core = cands[tgt]
    else:
        tgt = ORDER[(ORDER.index(cur) + 1) % len(ORDER)]
        lead = trail = 0
        core = "".join(convert(keys, tgt))
    return tgt, lead, trail, core


def make_plan(keys, tgt, lead, trail, core, sep_in_app, sep_vk, prefix=None):
    """sep_in_app: роздільник уже в програмі (треба стерти); sep_vk: яким роздільником закінчити.
    prefix: (скільки Backspace, новий текст, старий текст) — для попереднього однолітерного слова."""
    n = len(keys)
    text = "".join(k.ch for k in keys[:lead]) + core + "".join(k.ch for k in keys[n - trail:])
    if sep_vk == 0x20:
        text += " "
    bs, orig = n + (1 if sep_in_app else 0), "".join(k.ch for k in keys)
    if prefix:
        bs, text, orig = bs + prefix[0], prefix[1] + text, prefix[2] + orig
    return Plan(bs, text, tgt, sep_vk, orig, keys[0].lang, "".join(k.ch for k in keys[lead:n - trail]))


# ───────────────────────────── Введення ─────────────────────────────────
def send_events(items):
    if not items:
        return
    arr = (INPUT * len(items))()
    for i, (vk, sc, fl) in enumerate(items):
        arr[i].type = 1
        arr[i].ki = KEYBDINPUT(vk, sc, fl, 0, MARK)
    user32.SendInput(len(items), arr, ctypes.sizeof(INPUT))


def sep_events(vk):
    return [(vk, SEP_SCAN[vk], 0), (vk, SEP_SCAN[vk], KEYEVENTF_KEYUP)]


def run_plan(plan):
    BUSY_T[0] = time.time()
    time.sleep(0.01)
    foc = focus_hwnd()
    dbg("план: стерти", plan.bs, "надрукувати", repr(plan.text), "->", plan.tgt)
    for _ in range(plan.bs):                          # по одному Backspace із паузою: так надійніше
        send_events([(0x08, 0x0E, 0), (0x08, 0x0E, KEYEVENTF_KEYUP)])
        time.sleep(KEY_DELAY)
    time.sleep(0.03)
    for ch in plan.text:
        send_events([(0, ord(ch), KEYEVENTF_UNICODE), (0, ord(ch), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)])
        time.sleep(KEY_DELAY)
    if plan.sep in (0x0D, 0x09):
        send_events(sep_events(plan.sep))
    # Спершу даємо програмі дообробити правку, і лише ПОТІМ перемикаємо розкладку:
    # перемикання посеред правки (Блокнот Win11) «з'їдає» частину Backspace і перші символи.
    time.sleep(0.05 + KEY_DELAY * (plan.bs + len(plan.text)))
    if lang_of(layout_of(foc)) != plan.tgt:
        user32.PostMessageW(foc, WM_INPUTLANGCHANGEREQUEST, 0, HKL[plan.tgt])
        for _ in range(40):                           # чекаємо, поки розкладка справді перемкнеться
            if lang_of(layout_of(foc)) == plan.tgt:
                break
            time.sleep(0.01)
        time.sleep(0.06)
    if plan.tgt in ("uk", "ru"):
        S.cyr = plan.tgt
    tray_refresh()


# ───────────────────────────── Стан і черга ─────────────────────────────
class S:
    buf, last, hwnd, t = [], None, 0, 0.0
    auto = AUTO_ON_START
    learn = LEARN_ON_START
    cyr = PREFERRED
    corr = None                 # (час, Plan) останньої автокорекції, поки після неї нічого не набрано
    prev = None                 # (keys, час) попереднього однолітерного слова, якщо його не виправляли
    flag = FLAG_ON_START
    fly = FLY_ON_START
    fly_min = FLY_MIN_START
    fly_done = False            # у цьому слові «на льоту» вже виправляли (більше не чіпаємо до кінця слова)
    lang = None                 # поточна мова розкладки у вікні з фокусом (для прапора)
    ctx = deque(maxlen=6)       # мови останніх слів поточного речення (контекст)


jobs = queue.Queue()
LOCK = threading.RLock()
BUSY, BUSY_T = [0], [0.0]      # BUSY > 0: клавіатуру «затримуємо», події йдуть у PENDING
PENDING = []                   # (vk, scan, flags, is_up, mods)
DOWN = set()                   # модифікатори, які зараз натиснуті (за реальними подіями)


def mods():
    return (bool(DOWN & {0xA0, 0xA1}), bool(DOWN & {0xA2, 0xA3}),
            bool(DOWN & {0xA4, 0xA5}), bool(DOWN & {0x5B, 0x5C}))


def schedule(plan):
    with LOCK:
        BUSY[0] += 1
        BUSY_T[0] = time.time()
    jobs.put(plan)


def to_events(batch):
    out = []
    for vk, sc, flags, is_up, _m in batch:
        fl = (KEYEVENTF_KEYUP if is_up else 0) | (KEYEVENTF_EXTENDED if flags & LLKHF_EXTENDED else 0)
        out.append((vk, sc, fl))
    return out


def drain():
    """Відтворює натискання, які ми затримали, і знімає «затримку»."""
    while True:
        with LOCK:
            batch = PENDING[:]
            del PENDING[:]
            if not batch:
                BUSY[0] = max(0, BUSY[0] - 1)
                return
        for i, ev in enumerate(batch):
            vk, sc, flags, is_up, m = ev
            swallowed = False
            if not is_up:
                before = BUSY[0]
                swallowed = on_key(vk, sc, m)
                if BUSY[0] > before:                 # це натискання запустило наступну корекцію
                    with LOCK:
                        PENDING[0:0] = batch[i + 1:]
                        BUSY[0] = max(0, BUSY[0] - 1)
                    return
            if not swallowed:
                send_events(to_events([ev]))


def worker():
    try:
        spell_warmup()
    except Exception:
        pass
    while True:
        plan = jobs.get()
        try:
            run_plan(plan)
        except Exception:
            if plan.sep in SEP_SCAN:
                send_events(sep_events(plan.sep))
        try:
            drain()
        except Exception:
            with LOCK:
                BUSY[0] = 0
                lost = PENDING[:]
                del PENDING[:]
            send_events(to_events(lost))


def reset():
    S.buf.clear()
    S.last = None
    S.corr = None
    S.prev = None
    S.fly_done = False
    S.ctx.clear()


def quit_app():
    user32.PostThreadMessageW(MAIN_TID, 0x12, 0, 0)      # WM_QUIT головному потоку


def toggle_auto():
    S.auto = not S.auto
    tray_refresh()
    threading.Thread(target=winsound.Beep, args=(900 if S.auto else 500, 120), daemon=True).start()


# ───────────────────────────── Трей ─────────────────────────────────────
WM_TRAY = 0x401
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
TASKBAR_CREATED = user32.RegisterWindowMessageW("TaskbarCreated")
TRAY = {"hwnd": None, "icons": {}}


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT), ("uFlags", wt.UINT),
                ("uCallbackMessage", wt.UINT), ("hIcon", VP), ("szTip", wt.WCHAR * 128),
                ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD), ("szInfo", wt.WCHAR * 256),
                ("uVersion", wt.UINT), ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", VP)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wt.BOOL), ("xHotspot", wt.DWORD), ("yHotspot", wt.DWORD),
                ("hbmMask", VP), ("hbmColor", VP)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", VP), ("hIcon", VP), ("hCursor", VP),
                ("hbrBackground", VP), ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.SetTimer.argtypes = [wt.HWND, ctypes.c_size_t, wt.UINT, VP]
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wt.HWND, VP, VP, VP]
user32.CreateWindowExW.restype = wt.HWND


def icon_from_bgra(px):
    """HICON із 32×32 пікселів BGRA. Малюється в пам'яті, без файлів."""
    size = 32
    color = (ctypes.c_ubyte * len(px)).from_buffer(px)
    mask = (ctypes.c_ubyte * (size * size // 8))()
    info = ICONINFO(True, 0, 0, gdi32.CreateBitmap(size, size, 1, 1, mask),
                    gdi32.CreateBitmap(size, size, 1, 32, color))
    return user32.CreateIconIndirect(ctypes.byref(info))


def circle_bgra(rgb):
    """Кружечок: колір усередині, біле кільце (запасний значок, коли прапор вимкнено)."""
    size, r_, g_, b_ = 32, *rgb
    c, rad = (size - 1) / 2, size / 2 - 2
    px = bytearray()
    for y in range(size):
        for x in range(size):
            d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5
            if d <= rad - 3:
                px += bytes((b_, g_, r_, 255))
            elif d <= rad:
                px += bytes((255, 255, 255, 255))
            else:
                px += bytes((0, 0, 0, 0))
    return px


def _flag_pixel(lang, x, y):
    """Колір пікселя (x 0..31, y 0..21) у прапорі мови."""
    if lang == "uk":                                   # Україна: синій / жовтий
        return (0, 87, 183) if y < 11 else (255, 213, 0)
    if lang == "ru":                                   # Росія: білий / синій / червоний
        return (255, 255, 255) if y < 7 else ((0, 57, 166) if y < 15 else (213, 43, 30))
    if EN_FLAG == "gb":                                # Велика Британія (Union Jack)
        u, v = (x + 0.5) * 60 / 32, (y + 0.5) * 30 / 22
        d = min(abs(u - 2 * v), abs(u + 2 * v - 60)) / 2.236
        if abs(u - 30) <= 3 or abs(v - 15) <= 3:
            return (200, 16, 46)
        if abs(u - 30) <= 5 or abs(v - 15) <= 5:
            return (255, 255, 255)
        if d <= 1:
            return (200, 16, 46)
        return (255, 255, 255) if d <= 3 else (1, 33, 105)
    if x < 13 and y < 12:                              # США: синє поле з «зірками» + смуги
        return (255, 255, 255) if (x % 4 == 2 and y % 3 == 1) else (60, 59, 110)
    return (178, 34, 52) if int(y * 13 / 22) % 2 == 0 else (255, 255, 255)


def flag_bgra(lang, active=True):
    """Прапор мови 32×22 по центру значка 32×32; на паузі — сірий."""
    size, y0, h = 32, 5, 22
    px = bytearray(size * size * 4)
    for y in range(h):
        for x in range(size):
            r, g, b = (70, 70, 70) if x in (0, size - 1) or y in (0, h - 1) else _flag_pixel(lang, x, y)
            if not active:
                gray = (r * 30 + g * 59 + b * 11) // 100
                r = g = b = gray
            i = ((y0 + y) * size + x) * 4
            px[i:i + 4] = bytes((b, g, r, 255))
    return px


LANG_NAMES = {"en": "English", "uk": "Українська", "ru": "Русский"}


def tray_icon():
    key = (S.lang, S.auto) if (S.flag and S.lang in KLID) else ("circle", S.auto)
    if key not in TRAY["icons"]:
        TRAY["icons"][key] = icon_from_bgra(
            flag_bgra(S.lang, S.auto) if key[0] != "circle"
            else circle_bgra((40, 170, 70) if S.auto else (200, 60, 60)))
    return TRAY["icons"][key]


def poll_lang():
    """Яка розкладка зараз у вікні з фокусом. True, якщо мова змінилась."""
    foc = focus_hwnd()
    if not foc or foc == TRAY["hwnd"]:
        return False
    lang = lang_of(layout_of(foc))
    if lang and lang != S.lang:
        S.lang = lang
        return True
    return False


def tray_refresh():
    """Безпечно з будь-якого потоку: оновлення значка виконає головний потік."""
    if TRAY["hwnd"]:
        user32.PostMessageW(TRAY["hwnd"], 0x402, 0, None)


def tray_update(op=NIM_MODIFY):
    if not TRAY["hwnd"]:
        return
    nid = NOTIFYICONDATAW()
    nid.cbSize = ctypes.sizeof(nid)
    nid.hWnd, nid.uID = TRAY["hwnd"], 1
    nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    nid.uCallbackMessage = WM_TRAY
    nid.hIcon = tray_icon()
    nid.szTip = "LayoutSwitcher: " + (LANG_NAMES.get(S.lang, "?") + ", " if S.flag and S.lang else "") \
        + ("увімкнено" if S.auto else "на паузі")
    shell32.Shell_NotifyIconW(op, ctypes.byref(nid))


HELP_ADD_WORDS = """ЯК ПРАВИЛЬНО ДОДАВАТИ ВИНЯТКИ Й СЛОВА

1. Виняток для програми (там нічого не виправляти і не вчитись)

  • У меню трея оберіть «Редагувати чорний список…». Відкриється blacklist.txt поруч із програмою.
  • Додайте ім'я exe-файлу по одному в рядок (# починає коментар): code.exe, game.exe, chrome.exe.
  • Зміни підхоплюються самі, перезапуск не потрібен.
  • Ім'я exe видно у диспетчері завдань на вкладці «Подробиці».


2. Додати слово вручну (в тому числі як виняток: «не чіпай це слово»)

  • Слова записуються у learned.txt. Його відкриває пункт меню трея «Відкрити вивчені слова…». Файл лежить поруч із програмою, а якщо туди писати не можна, то в %APPDATA%\\LayoutSwitcher.
  • Кожен рядок має вигляд: мова, символ Tab, слово. Мови: en, uk, ru. Пробіли замість Tab не спрацюють. Приклади:

        en\tkubectl
        uk\tкібербулінг
        ru\tмессенджер

  • Слово з такого запису вважається правильним для цієї мови. Воно не перетвориться, коли ви набираєте його в тій самій розкладці. А якщо ви набрали його не в тій розкладці, програма перемкне його саме на цю мову. Це працює і для слів із 2–3 літер.
  • Після ручного редагування перезапустіть програму: цей файл читається лише при старті. Зберігайте файл у UTF-8.
  • Видалити слово: видаліть рядок. Стерти все: пункт меню «Забути всі вивчені слова».


3. Нічого не редагуючи, прямо під час роботи

  • Програма пропустила слово: натисніть Pause. Слово конвертується й запам'ятається, якщо схоже на справжнє.
  • Програма хибно виправила слово: натисніть Pause протягом 8 секунд. Корекція скасується, а початкове слово запишеться як правильне.
  • Слова, яких немає у словниках, але які ви тричі набрали правильно, потрапляють у learned.txt самі (якщо ввімкнено «Самонавчання»).


Великі словники words_*.txt краще не редагувати вручну. Свої слова додавайте в learned.txt: це простіше й не залежить від частотного порядку. Якщо все ж додаєте слова в кінець words_*.txt, слова з 2–3 літер це не врахує, бо для них важлива позиція в топі частоти.
"""

user32.MessageBoxW.argtypes = [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.UINT]


HELP_DICTS = """СЛОВНИКИ, МОДЕЛІ ТА НАВЧАННЯ З ДОКУМЕНТІВ

Програма впізнає, чи слово «своє» для мови, кількома способами:

  • ваші вивчені слова (learned.txt);
  • великі частотні списки words_*.txt (get_wordlists.bat, до 300 тисяч слів на мову);
  • словники Hunspell uk_UA, ru_RU, en_US з відмінками й формами слів: get_dictionaries.bat кладе їх у папку dictionaries поруч із програмою;
  • перевірка правопису Windows;
  • n-грамна мовна модель: вчиться на words_*.txt і оцінює, чи схоже невідоме слово на слово цієї мови;
  • пошук слів з однією опечаткою (пропущена, зайва або замінена літера);
  • контекст: мова попередніх слів речення трохи підсилює відповідну мову (допомагає відрізнити українську від російської).

Усе будується в пам'яті у фоні після запуску (кілька секунд). Сірий рядок у меню трея показує, що вже готове.


НАВЧАННЯ З ДОКУМЕНТІВ

  • Меню трея → «Навчити зі своїх документів…» → оберіть папку.
  • Програма прочитає файли .txt, .md, .csv, .html, .rtf, .docx, .odt, .fb2 (PDF не читається), порахує слова й занесе у learned.txt ті, яких немає у словниках і які трапились щонайменше двічі.
  • Усе відбувається на вашому комп'ютері, нічого нікуди не надсилається. Не обирайте папки з паролями чи конфіденційними записами.
  • Помилкові слова видаліть із learned.txt («Відкрити вивчені слова…») і перезапустіть програму.
  • За один запуск: до 5000 файлів, 400 МБ, 3 хвилини, 20000 нових слів.
"""


def show_help(text=None):
    """Довідка у вікні (окремий потік, щоб не блокувати трей і хуки)."""
    threading.Thread(target=lambda: user32.MessageBoxW(
        None, text or HELP_ADD_WORDS, "LayoutSwitcher: Help", 0x40 | 0x10000 | 0x40000), daemon=True).start()


def status_text():
    spell = [l for l in ORDER if spell_checker(l)]
    files = [l for l in ORDER if len(WORDS[l]) >= 1000]
    fly = "" if not S.fly else (f", на льоту від {S.fly_min} літер" if all(PFX[l] for l in KLID)
                                else ", на льоту: потрібні words_*.txt")
    return (f"Словники: Windows [{' '.join(spell) or '-'}], Hunspell [{' '.join(l for l in ORDER if l in HUN) or '-'}], "
            f"файли [{' '.join(files) or '-'}], моделі [{' '.join(l for l in ORDER if l in NGRAM) or '-'}], "
            f"вивчено {learned_total()}{fly}")


def show_menu(hwnd):
    menu = user32.CreatePopupMenu()
    user32.AppendMenuW(menu, 0x1, 0, status_text())                        # 0x1 = MF_GRAYED (інформація)
    user32.AppendMenuW(menu, 0x800, 0, None)                               # роздільник
    user32.AppendMenuW(menu, 0x8 if S.auto else 0, 1, "Автоперемикання")   # 0x8 = MF_CHECKED
    user32.AppendMenuW(menu, 0x8 if S.learn else 0, 5, "Самонавчання")
    user32.AppendMenuW(menu, 0x8 if S.flag else 0, 9, "Прапор мови в треї")
    user32.AppendMenuW(menu, 0x8 if S.fly else 0, 10, "Виправляти на льоту")
    fly = user32.CreatePopupMenu()
    for n, label in ((3, "3 літери"), (4, "4 літери"), (5, "5 літер")):
        user32.AppendMenuW(fly, 0x8 if S.fly_min == n else 0, 10 + n, label)
    user32.AppendMenuW(menu, 0x10, fly, "Поріг для режиму «на льоту»")
    user32.AppendMenuW(menu, 0x8 if autostart_enabled() else 0, 4, "Запускати разом з Windows")
    user32.AppendMenuW(menu, 0x800, 0, None)
    user32.AppendMenuW(menu, 0, 6, "Відкрити вивчені слова…")
    user32.AppendMenuW(menu, 0, 16, "Навчити зі своїх документів…")
    user32.AppendMenuW(menu, 0, 7, "Забути всі вивчені слова")
    user32.AppendMenuW(menu, 0, 2, "Редагувати чорний список…")
    user32.AppendMenuW(menu, 0x800, 0, None)
    sub = user32.CreatePopupMenu()
    user32.AppendMenuW(sub, 0, 8, "Як правильно додавати слова у чорний список або слова в словники")
    user32.AppendMenuW(sub, 0, 17, "Словники, моделі та навчання з документів")
    user32.AppendMenuW(menu, 0x10, sub, "Help")                            # 0x10 = MF_POPUP (підменю)
    user32.AppendMenuW(menu, 0, 3, "Вийти")
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.SetForegroundWindow(hwnd)
    cmd = user32.TrackPopupMenu(menu, 0x100 | 0x2, pt.x, pt.y, 0, hwnd, None)   # RETURNCMD | RIGHTBUTTON
    user32.PostMessageW(hwnd, 0, 0, None)
    user32.DestroyMenu(menu)
    if cmd == 1:
        toggle_auto()
    elif cmd == 2:
        open_blacklist()
    elif cmd == 3:
        quit_app()
    elif cmd == 4:
        set_autostart(not autostart_enabled())
    elif cmd == 5:
        S.learn = not S.learn
        save_setting("Learn", S.learn)
    elif cmd == 10:
        S.fly = not S.fly
        save_setting("Fly", S.fly)
    elif cmd in (13, 14, 15):
        S.fly_min = cmd - 10
        save_setting("FlyMin", S.fly_min)
    elif cmd == 9:
        S.flag = not S.flag
        save_setting("Flag", S.flag)
        poll_lang()
        tray_update()
    elif cmd == 6 and LEARN_PATH:
        os.startfile(LEARN_PATH)
    elif cmd == 7:
        forget_all()
    elif cmd == 8:
        show_help()
    elif cmd == 17:
        show_help(HELP_DICTS)
    elif cmd == 16:
        threading.Thread(target=learn_from_documents, daemon=True).start()


@WNDPROC
def wndproc(hwnd, msg, wparam, lparam):
    try:
        if msg == WM_TRAY:
            if lparam == 0x203:                  # подвійний клік лівою
                toggle_auto()
            elif lparam in (0x205, 0x7B):        # права кнопка / контекстне меню
                show_menu(hwnd)
            return 0
        if msg == 0x113:                         # WM_TIMER: чи змінилась розкладка
            if S.flag and poll_lang():
                tray_update()
            return 0
        if msg == 0x402:                         # запит на оновлення значка з іншого потоку
            poll_lang()
            tray_update()
            return 0
        if msg == TASKBAR_CREATED:               # Провідник перезапустився
            tray_update(NIM_ADD)
            return 0
    except Exception:
        pass
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def tray_init():
    hinst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW()
    wc.lpfnWndProc, wc.hInstance, wc.lpszClassName = wndproc, hinst, "LayoutSwitcherTray"
    user32.RegisterClassW(ctypes.byref(wc))
    TRAY["hwnd"] = user32.CreateWindowExW(0, "LayoutSwitcherTray", "LayoutSwitcher", 0,
                                          0, 0, 0, 0, None, None, hinst, None)
    poll_lang()
    tray_update(NIM_ADD)
    user32.SetTimer(TRAY["hwnd"], 1, 250, None)


# ───────────────────────────── Хуки ─────────────────────────────────────
def fix_prev(keys, sep_vk):
    """Однолітерне слово («z») набране не в тій розкладці, а наступне слово — правильне: виправляємо обидва."""
    pv = S.prev
    if not pv or time.time() - pv[1] > 6 or len({k.lang for k in keys}) > 1:
        return None
    pk, l2 = pv[0], keys[0].lang
    l1 = pk[0].lang
    word = "".join(k.ch for k in keys)
    core = word.strip("".join({c for c in word if not c.isalpha()}))
    if l1 == l2 or len(core) < 2 or score(core, l2) != 1.0:
        return None
    pc = convert(pk, l2)[0]
    if pk[0].ch.lower() in ONE[l1] or pc.lower() not in ONE[l2]:
        return None
    text = pc + " " + word + (" " if sep_vk == 0x20 else "")
    return Plan(len(pk) + 1 + len(keys), text, l2, sep_vk, pk[0].ch + " " + word, l1, pk[0].ch)


def fly_decide(keys):
    """Посеред слова: початок «неможливий» у поточній мові й упевнено можливий в іншій → мова, або None."""
    n = len(keys)
    if not (S.fly_min <= n <= 6) or len({k.lang for k in keys}) > 1:
        return None
    cur = keys[0].lang
    if not PFX[cur]:
        return None                                   # без words_*.txt «неможливе» довести не можна
    raw = "".join(k.ch for k in keys)
    if any(c.isdigit() for c in raw) or (any(c.isupper() for c in raw[1:]) and not raw.isupper()):
        return None
    low = raw.lower()
    if low.isalpha() and PFX[cur].get(low, 0) > 0:
        return None                                   # таке слово в поточній мові існує
    best = None
    for lang in KLID:
        if lang == cur or not PFX[lang]:
            continue
        conv = "".join(convert(keys, lang)).lower()
        if not conv.isalpha():
            continue
        if (lang == "uk" and any(c in RU_ONLY for c in conv)) or (lang == "ru" and any(c in UK_ONLY for c in conv)):
            continue
        cnt = PFX[lang].get(conv, 0)
        if cnt < FLY_ALT_MIN:
            continue
        w = cnt * (1.5 if lang == S.cyr else 1.0)
        if best is None or w > best[0]:
            best = (w, lang)
    return best[1] if best else None


def try_fly(keys, foc):
    """Виправлення посеред слова. Натискання, що його спричинило, «з'їдається» й друкується корекцією."""
    tgt = fly_decide(keys)
    if not tgt or app_excluded(foc):
        return False
    conv = convert(keys, tgt)
    plan = Plan(len(keys) - 1, "".join(conv), tgt, 0, "".join(k.ch for k in keys), keys[0].lang,
                "".join(k.ch for k in keys))
    dbg("на льоту:", repr(plan.orig), "->", repr(plan.text), tgt)
    S.buf[:] = [Key(k.vk, k.sc, k.shift, k.caps, c, tgt) for k, c in zip(keys, conv)]
    S.fly_done = True
    S.last = None
    S.corr = (time.time(), plan, list(keys))
    schedule(plan)
    return True


def try_correct(keys, foc, sep_vk):
    """Автокорекція слова при натисканні роздільника. True — роздільник «з'їдено» (його надрукує корекція)."""
    d = decide(keys, True) if S.auto else None
    if d and not app_excluded(foc):
        prefix, pv = None, S.prev
        if pv and time.time() - pv[1] < 6 and pv[0][0].lang == keys[0].lang:
            pk = pv[0]
            pc = convert(pk, d[0])[0]
            # «Z» перед виправленим словом: не слово цієї мови, а в новій мові — «Я»
            if pk[0].ch.lower() not in ONE[pk[0].lang] and pc.lower() in ONE[d[0]]:
                prefix = (2, pc + " ", pk[0].ch + " ")
        plan = make_plan(keys, *d, False, sep_vk, prefix)
        dbg("виправляю:", repr(plan.orig), "->", repr(plan.text), plan.tgt)
        if len(d[3]) >= 3:
            S.ctx.append(d[0])
        S.last = None
        S.prev = None
        S.corr = (time.time(), plan, None) if sep_vk == 0x20 else None
        schedule(plan)
        return True
    if S.auto and S.prev and not app_excluded(foc):
        plan = fix_prev(keys, sep_vk)
        if plan:
            dbg("виправляю попереднє слово:", repr(plan.orig), "->", repr(plan.text), plan.tgt)
            S.ctx.append(plan.tgt)
            S.prev = S.last = None
            S.corr = (time.time(), plan, None) if sep_vk == 0x20 else None
            schedule(plan)
            return True
    note_word(keys)
    observe(keys, foc)
    return False


def on_key(vk, sc, m):
    """Обробляє натискання. True — «з'їсти» його (Pause або роздільник, який замінюється корекцією)."""
    shift, ctrl, alt, win = m
    if vk == 0x13:                                    # Pause
        if ctrl:
            quit_app()
        elif shift:
            toggle_auto()
        else:
            foc = focus_hwnd()
            corr, keys, sep_in_app = S.corr, list(S.buf), False
            if corr and time.time() - corr[0] < UNDO_WINDOW and (not keys or corr[1].sep == 0):
                # скасування автокорекції: повертаємо як було й запам'ятовуємо слово як правильне
                p = corr[1]
                tail = " " if p.sep == 0x20 else ""
                if p.sep:
                    maybe_learn(p.orig_lang, p.orig_core)     # не вчимо сміття, лише схоже на слово
                schedule(Plan(len(p.text), p.orig + tail, p.orig_lang, 0x20 if tail else 0, "", "", ""))
                if corr[2]:                                   # «на льоту»: слово лишається в буфері як було
                    reset()
                    S.buf[:] = corr[2]
                    S.fly_done = True                         # у цьому слові більше не чіпаємо
                    return True
            else:
                if not keys and S.last:
                    keys, sep_in_app = list(S.last), True
                d = decide(keys, False) if keys else None
                if d and not app_excluded(foc):
                    tgt, lead, trail, core = d
                    schedule(make_plan(keys, tgt, lead, trail, core, sep_in_app, 0x20 if sep_in_app else 0))
                    maybe_learn(tgt, core)            # ручна корекція = навчання
            reset()
        return True
    if vk in MODS:
        return False

    now, foc = time.time(), focus_hwnd()
    if foc != S.hwnd or now - S.t > IDLE_RESET:
        reset()
    S.hwnd, S.t = foc, now

    if ctrl or alt or win:
        reset()
        return False
    if vk in (0x20, 0x0D, 0x09):                      # пробіл / Enter / Tab: кінець слова
        S.corr = None
        S.fly_done = False
        if S.buf:
            keys = list(S.buf)
            S.buf.clear()
            if try_correct(keys, foc, vk):
                if vk != 0x20:
                    S.ctx.clear()
                return True
            S.last = keys if vk == 0x20 else None
            S.prev = (keys, now) if (vk == 0x20 and len(keys) == 1) else None
        elif vk != 0x20:
            S.last = None
            S.prev = None
        if vk != 0x20:
            S.ctx.clear()
        return False
    if vk == 0x08:
        if S.buf:
            S.buf.pop()
        S.last = None
        S.corr = None
        S.prev = None
        return False
    if vk in NAV:
        reset()
        return False

    if is_password_field(foc):
        reset()
        return False
    hkl = layout_of(foc)
    lang = lang_of(hkl)
    if lang is None:
        reset()
        return False
    if lang in ("uk", "ru"):
        S.cyr = lang
    caps = bool(user32.GetKeyState(0x14) & 1)
    ch = vk_to_char(vk, sc, shift, caps, hkl)
    if ch and ch.isprintable():
        S.buf.append(Key(vk, sc, shift, caps, ch, lang))
        S.last = None
        S.corr = None
        if S.fly and S.auto and not S.fly_done and len(S.buf) >= S.fly_min and try_fly(list(S.buf), foc):
            return True
    else:
        reset()
    return False


@HOOKPROC
def hook(n_code, w_param, l_param):
    try:
        if n_code == 0:
            k = ctypes.cast(l_param, ctypes.POINTER(KBDLL)).contents
            if not (k.flags & LLKHF_INJECTED):         # власні (injected) події пропускаємо
                vk, is_up = k.vkCode, bool(k.flags & LLKHF_UP)
                if vk in (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0x5B, 0x5C):
                    (DOWN.discard if is_up else DOWN.add)(vk)
                m = mods()
                with LOCK:
                    if BUSY[0] > 0 and time.time() - BUSY_T[0] > HOLD_LIMIT:
                        BUSY[0] = 0                    # аварійне відпускання: нічого не «застрягає»
                        lost = PENDING[:]
                        del PENDING[:]
                        send_events(to_events(lost))
                    if BUSY[0] > 0:
                        PENDING.append((vk, k.scanCode, k.flags, is_up, m))
                        return 1
                if not is_up and on_key(vk, k.scanCode, m):
                    return 1
    except Exception:
        pass
    return user32.CallNextHookEx(None, n_code, w_param, l_param)


@HOOKPROC
def mouse_hook(n_code, w_param, l_param):
    # Лише факт натискання кнопки: курсор міг переміститися, тож поточне слово скидаємо.
    if n_code == 0 and w_param in (0x201, 0x204, 0x207, 0x20B):
        reset()
    return user32.CallNextHookEx(None, n_code, w_param, l_param)


def main():
    if DEBUG:
        kernel32.AllocConsole()
        try:
            sys.stdout = open("CONOUT$", "w", encoding="utf-8")
        except OSError:
            pass
        print("LayoutSwitcher --debug: слова, які виправляються, друкуються тут. Закрийте вікно, щоб вийти.")
    # Один екземпляр: інакше два хуки виправляли б кожне слово двічі.
    _mutex = kernel32.CreateMutexW(None, False, "Local\\LayoutSwitcherSingleton")
    if ctypes.get_last_error() == 183:      # ERROR_ALREADY_EXISTS
        return
    load_settings()
    load_learned()
    try:
        spell_warmup()                      # прогріваємо словники ДО встановлення хука
    except Exception:
        pass
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=build_models, daemon=True).start()
    hmod = kernel32.GetModuleHandleW(None)
    if not user32.SetWindowsHookExW(WH_KEYBOARD_LL, hook, hmod, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    user32.SetWindowsHookExW(WH_MOUSE_LL, mouse_hook, hmod, 0)
    tray_init()
    msg = wt.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        tray_update(NIM_DELETE)


if __name__ == "__main__":
    main()
