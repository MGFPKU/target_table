import os
import json
from typing import Dict

LANG: str = os.getenv("LANGUAGE", "CN").upper()
translation: Dict[str, str] = {}

if LANG not in ['CN', 'EN']:
    raise ValueError(f"Unsupported language: {LANG}")

if LANG == 'EN':
    try:
        with open('translation.json', 'r', encoding='utf-8') as f:
            translation = json.load(f)
            # ensure str->str mapping
            if not isinstance(translation, dict):
                translation = {}
            else:
                translation = {str(k): str(v) for k, v in translation.items()}
    except Exception:
        # If the file can't be read, keep an empty mapping so lookups fall back to key
        translation = {}

def i18n(key: str, *args, **kwargs) -> str:
    """
    Return localized string. Supports placeholders via Python str.format:
      i18n("Hello, {}!", "Alice") -> "Hello, Alice!"
      i18n("Welcome, {name}", name="Bob") -> "Welcome, Bob"

    If formatting fails, returns the unformatted result.
    """
    if LANG == 'CN':
        result = key
    else:
        result = translation.get(key, key)

    if not args and not kwargs:
        return result

    try:
        return result.format(*args, **kwargs)
    except Exception:
        # On any formatting error, return the raw (unformatted) result
        return result
