from __future__ import annotations

import re


DEFAULT_LANGUAGE = "en"

_LANGUAGE_ALIASES = {
    "english": "en",
    "en-us": "en",
    "en-gb": "en",
    "chinese": "zh",
    "mandarin": "zh",
    "simplified-chinese": "zh",
    "traditional-chinese": "zh",
    "zh-cn": "zh",
    "zh-tw": "zh",
    "zh-hans": "zh",
    "zh-hant": "zh",
    "spanish": "es",
    "es-es": "es",
    "es-mx": "es",
}


def normalize_language_code(language: str | None) -> str:
    if not language:
        return DEFAULT_LANGUAGE

    normalized = language.strip().lower().replace("_", "-").replace(" ", "-")
    if not normalized:
        return DEFAULT_LANGUAGE

    normalized = re.sub(r"[^a-z-]", "", normalized)
    if not normalized:
        return DEFAULT_LANGUAGE

    if normalized in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[normalized]

    primary = normalized.split("-", 1)[0]
    if primary:
        return primary
    return DEFAULT_LANGUAGE


def language_instruction(language: str | None) -> str:
    normalized = normalize_language_code(language)
    if normalized == "zh":
        return "Chinese"
    if normalized == "en":
        return "English"
    return f"the user's language ({normalized})"
