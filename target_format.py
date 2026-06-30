"""Format the "Target" display column from its constituent parts."""

import re

# Chinese numeral to integer mapping for FYP year computation
CN_NUMERALS: dict[str, int] = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
}


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.strip().upper() in {"", "N/A", "NA", "NONE", "NULL"}:
        return ""
    text = re.sub(r"[​‌‍﻿]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _get_fyp_year_range(ordinal_str: str) -> str | None:
    """Compute the year range for a given FYP ordinal (e.g., "10th" → "2001-2005").

    The 10th FYP spans 2001–2005; each subsequent plan shifts forward by 5 years.
    """
    match = re.fullmatch(r"(\d+)(?:st|nd|rd|th)", ordinal_str)
    if not match:
        return None
    n = int(match.group(1))
    start_year = 2001 + (n - 10) * 5
    return f"{start_year}-{start_year + 4}"


def _starts_with_letter(text: str) -> bool:
    """Return True if *text* starts with a letter — we assume it already
    contains a preposition and doesn't need "during" prepended."""
    stripped = text.strip()
    return bool(stripped) and stripped[0].isalpha()


def format_target(parts: dict[str, object]) -> str:
    direction = clean_text(parts.get("Direction"))
    magnitude = clean_text(parts.get("Target_Magnitude"))
    baseline = clean_text(parts.get("Baseline"))
    horizon = clean_text(parts.get("Target_Year_or_Period"))

    target_phrase = " ".join(part for part in [direction, magnitude] if part)
    if baseline:
        target_phrase = (
            f"{target_phrase} from {baseline} levels"
            if target_phrase
            else f"from {baseline} levels"
        )

    if horizon:
        fyp_match = re.fullmatch(
            r"(the\s+)?(?P<ordinal>\d+(?:st|nd|rd|th))\s+FYP",
            horizon,
            flags=re.IGNORECASE,
        )
        if fyp_match:
            ordinal = fyp_match.group("ordinal")
            year_range = _get_fyp_year_range(ordinal.lower())
            period = f"the {ordinal} FYP"
            if year_range:
                period = f"{period} ({year_range})"
            prefix = f"during {period}"
        elif re.fullmatch(r"\d{4}", horizon):
            prefix = f"by {horizon}"
        elif _starts_with_letter(horizon):
            prefix = horizon
        else:
            prefix = f"during {horizon}"

        if target_phrase:
            # When there is no magnitude (just a bare direction word like "Achieve"),
            # place it before the horizon: "Achieve before 2060".
            # When there is a substantive target, keep the original order:
            # "by 2025, achieve 130 million tons".
            if not magnitude:
                return f"{target_phrase} {prefix}"
            else:
                return f"{prefix}, {target_phrase}"
        return prefix

    return target_phrase or "N/A"


def _get_cn_fyp_year_range(fyp_str: str) -> str | None:
    """Compute the year range for a Chinese FYP string (e.g., '十二五' → '2011-2015').

    Chinese FYP pattern: 十([一二三四五六七八九])?五
    - 十五  = 10th FYP (2001-2005)
    - 十一五 = 11th FYP (2006-2010)
    - 十二五 = 12th FYP (2011-2015)
    - 十三五 = 13th FYP (2016-2020)
    - etc.
    """
    match = re.fullmatch(r"十([一二三四五六七八九])?五", fyp_str)
    if not match:
        return None
    digit_char = match.group(1)
    n = 10 + (CN_NUMERALS.get(digit_char, 0) if digit_char else 0)
    start_year = 2001 + (n - 10) * 5
    return f"{start_year}-{start_year + 4}"


def format_target_cn(parts: dict[str, object]) -> str:
    """Format target display for Chinese content.

    Handles Chinese FYP shorthand, date patterns, and baseline prefixes.
    The raw data columns already contain Chinese text; this function arranges
    them into a natural Chinese reading order.

    Returns Chinese text like:
        "到2030年，实现1.3亿吨"
        "十三五期间（2016-2020），下降18%"
        "在2020年水平基础上，降低3.1%以上"
    """
    direction = clean_text(parts.get("Direction"))
    magnitude = clean_text(parts.get("Target_Magnitude"))
    baseline = clean_text(parts.get("Baseline"))
    horizon = clean_text(parts.get("Target_Year_or_Period"))

    elements: list[str] = []

    # --- Horizon phrase ---
    if horizon:
        # Chinese FYP shorthand: 十三五, 十二五, etc.
        fyp_match = re.fullmatch(r"十([一二三四五六七八九])?五", horizon)
        if fyp_match:
            year_range = _get_cn_fyp_year_range(horizon)
            if year_range:
                elements.append(f"{horizon}期间（{year_range}）")
            else:
                elements.append(f"{horizon}期间")
        elif re.fullmatch(r"\d{4}", horizon):
            elements.append(f"到{horizon}年")
        elif re.fullmatch(r"\d{4}年前", horizon) or re.fullmatch(r"\d{4}年左右", horizon):
            elements.append(f"在{horizon}")
        elif re.match(r"\d{4}[-–]\d{4}", horizon):
            elements.append(f"{horizon}期间")
        elif _starts_with_letter(horizon):
            elements.append(horizon)
        else:
            elements.append(f"在{horizon}")

    # --- Baseline phrase ---
    if baseline:
        if baseline.isdigit():
            elements.append(f"在{baseline}年水平基础上")
        else:
            elements.append(f"在{baseline}水平基础上")

    # --- Direction + magnitude (Chinese convention: no space) ---
    if direction and magnitude:
        elements.append(f"{direction}{magnitude}")
    elif direction:
        elements.append(direction)
    elif magnitude:
        elements.append(magnitude)

    if not elements:
        return "无"

    return "，".join(elements)
