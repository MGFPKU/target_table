"""Format the "Target" display column from its constituent parts."""

import re


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
