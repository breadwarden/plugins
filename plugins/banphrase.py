"""Banned phrases helper: load/save and robust matching.

Provides:
- `load_banned_phrases()` -> list[str]
- `save_banned_phrases(list)`
- `add_banned_phrase(phrase)` -> bool
- `remove_banned_phrase(phrase)` -> bool
- `contains_banned(text)` -> bool

Normalization: Unicode NFKD decomposition, remove diacritics, map common
cyrillic lookalikes and simple leet substitutions, lowercase and strip
non-alphanumeric characters before substring matching.
"""
from pathlib import Path
import json
import unicodedata
import re

BASE_DIR = Path(__file__).resolve().parent
BANNED_PHRASES_FILE = BASE_DIR / 'banned_phrases.json'

# simple leet map
_LEET = str.maketrans({"@": "a", "4": "a", "3": "e", "1": "i", "0": "o", "$": "s", "5": "s", "7": "t"})

# map common Cyrillic characters that look like Latin letters to Latin equivalents
_CYRILLIC_MAP = str.maketrans({
    ord('а'): 'a', ord('А'): 'a', ord('в'): 'v', ord('В'): 'v', ord('е'): 'e', ord('Е'): 'e',
    ord('ё'): 'e', ord('Ё'): 'e', ord('з'): 'z', ord('З'): 'z', ord('и'): 'i', ord('И'): 'i',
    ord('к'): 'k', ord('К'): 'k', ord('м'): 'm', ord('М'): 'm', ord('н'): 'n', ord('Н'): 'n',
    ord('о'): 'o', ord('О'): 'o', ord('р'): 'p', ord('Р'): 'p', ord('с'): 's', ord('С'): 's',
    ord('т'): 't', ord('Т'): 't', ord('у'): 'y', ord('У'): 'y', ord('х'): 'x', ord('Х'): 'x',
    ord('ь'): '', ord('Ь'): '', ord('ы'): 'y', ord('Ы'): 'y', ord('і'): 'i', ord('І'): 'i',
    ord('ј'): 'j', ord('Ј'): 'j'
})


def _normalise_text(text: str) -> str:
    if not text:
        return ""
    s = str(text)
    # decompose accents
    s = unicodedata.normalize('NFKD', s)
    # map cyrillic lookalikes
    s = s.translate(_CYRILLIC_MAP)
    # apply leet substitutions
    s = s.translate(_LEET)
    s = s.lower()
    # remove combining marks (diacritics)
    s = ''.join(ch for ch in unicodedata.normalize('NFKD', s) if not unicodedata.combining(ch))
    # keep only a-z0-9
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def load_banned_phrases():
    try:
        if BANNED_PHRASES_FILE.exists():
            data = json.loads(BANNED_PHRASES_FILE.read_text(encoding='utf-8'))
            if isinstance(data, list):
                return [str(x) for x in data]
    except Exception:
        pass
    return []


def save_banned_phrases(phrases):
    try:
        BANNED_PHRASES_FILE.write_text(json.dumps(list(phrases), ensure_ascii=False, indent=2), encoding='utf-8')
        return True
    except Exception:
        return False


def add_banned_phrase(phrase: str):
    phrase = (phrase or '').strip()
    if not phrase:
        return False
    phrases = load_banned_phrases()
    norms = { _normalise_text(p) for p in phrases }
    if _normalise_text(phrase) in norms:
        return False
    phrases.append(phrase)
    return save_banned_phrases(phrases)


def remove_banned_phrase(phrase: str):
    phrase = (phrase or '').strip()
    if not phrase:
        return False
    phrases = load_banned_phrases()
    target = _normalise_text(phrase)
    new = [p for p in phrases if _normalise_text(p) != target]
    if len(new) == len(phrases):
        return False
    return save_banned_phrases(new)


def contains_banned(text: str) -> bool:
    if not text:
        return False
    content = _normalise_text(text)
    if not content:
        return False
    for p in load_banned_phrases():
        np = _normalise_text(p)
        if np and np in content:
            return True
    return False
