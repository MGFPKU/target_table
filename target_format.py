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


def _extract_year(text: str) -> int | None:
    match = re.fullmatch(r"(\d{4})(?:\.0+)?", text)
    if not match:
        return None
    return int(match.group(1))


def format_target(parts: dict[str, object]) -> str:
    direction = clean_text(parts.get("Direction"))
    magnitude = clean_text(parts.get("Target_Magnitude"))
    baseline = clean_text(parts.get("Baseline"))
    horizon = clean_text(parts.get("Target_Year_or_Period"))
    announced_year = _extract_year(clean_text(parts.get("Announcement_Year")))

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
            target_year = int(horizon)
            if announced_year in (target_year, target_year - 1):
                prefix = f"in {horizon}"
            else:
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


# Groups of semantically equivalent Chinese direction verbs.
# When the magnitude starts with a member of the same group as the
# direction, the magnitude is already self-contained — use it alone.
# This avoids concatenations like "降低下降10%" → "下降10%".
_REDUCE_VERBS = frozenset({"降低", "下降", "减少", "削减"})
_INCREASE_VERBS = frozenset({"提高", "提升", "增长", "增加", "扩大", "年均增长"})
_ACHIEVE_VERBS = frozenset({"达到", "实现", "完成", "基本完成"})
_LIMIT_VERBS = frozenset({"控制在", "限制在", "约束在", "稳定在", "保持在"})
_EQUIV_GROUPS: tuple[frozenset[str], ...] = (
    _REDUCE_VERBS,
    _INCREASE_VERBS,
    _ACHIEVE_VERBS,
    _LIMIT_VERBS,
)

# Modifier prefixes that may appear before the verb in a magnitude string.
# E.g. "约下降4%" → strip "约" → check verb "下降"
_MODIFIER_PREFIXES = (
    "约", "大约", "力争", "至少", "不低于", "不超过",
    "超过", "基本", "全面", "逐步", "逐年", "持续",
    "大幅", "显著", "有效", "进一步",
)


def _strip_modifiers(text: str) -> str:
    """Strip known modifier prefixes from the start of *text*."""
    for prefix in _MODIFIER_PREFIXES:
        if text.startswith(prefix) and len(text) > len(prefix):
            return text[len(prefix):]
    return text


def _magnitude_is_self_contained(direction: str, magnitude: str) -> bool:
    """Return True if the magnitude already incorporates the direction verb.

    This handles cases where the magnitude field repeats or replaces the
    direction verb, making concatenation redundant (e.g. "降低" + "下降10%"
    should just be "下降10%", not "降低下降10%").
    """
    # Direct overlap: direction appears anywhere in the magnitude
    if direction in magnitude:
        return True

    # Check if magnitude starts with (possibly modified by an adverb)
    # an equivalent verb from the same group.
    # E.g. direction="降低", magnitude="约下降4%" → strip "约" → "下降4%" matches.
    magnitude_stem = _strip_modifiers(magnitude)
    if magnitude_stem != magnitude:
        if _magnitude_is_self_contained(direction, magnitude_stem):
            return True

    # Semantic overlap: magnitude starts with an equivalent verb from the
    # same group (e.g. direction="降低", magnitude starts with "下降")
    for group in _EQUIV_GROUPS:
        if direction in group:
            for verb in group:
                if magnitude.startswith(verb):
                    return True
            break  # direction belongs to exactly one group

    return False


def _build_target_phrase(direction: str, magnitude: str) -> str:
    """Build the Chinese target phrase from direction and magnitude.

    Handles the common overlap case where the magnitude text already
    incorporates the direction verb (e.g. direction="降低", magnitude="下降10%").
    Also handles magnitudes that start with comparative markers (比/较/相比).
    """
    if not direction and not magnitude:
        return ""
    if not magnitude:
        return direction
    if not direction:
        return magnitude

    # Magnitude already incorporates the direction → use magnitude alone
    if _magnitude_is_self_contained(direction, magnitude):
        return magnitude

    # Magnitudes starting with 比／较／相比 are comparative phrases
    # that are already self-contained target descriptions.
    if magnitude[:1] in ("比", "较") or magnitude.startswith("相比"):
        return magnitude

    # Standard concatenation — Chinese uses no space between verb and object.
    return direction + magnitude


def _has_self_contained_comparison(magnitude: str) -> bool:
    """Return True if the magnitude text already contains a comparative
    reference (比/较/相比), making a separate baseline prefix redundant."""
    return bool(magnitude) and (
        magnitude[:1] in ("比", "较") or magnitude.startswith("相比")
    )


def format_target_cn(parts: dict[str, object]) -> str:
    """Format target display for Chinese content.

    Handles Chinese FYP shorthand, date patterns, and baseline prefixes.
    The raw data columns already contain Chinese text; this function arranges
    them into a natural Chinese reading order.

    Returns Chinese text like:
        "到2030年，实现1.3亿吨"
        "十三五期间（2016-2020），较2015年下降18%"
        "到2020年，在2002年基础上降低10%"
        "2030年前，达峰"
    """
    direction = clean_text(parts.get("Direction"))
    magnitude = clean_text(parts.get("Target_Magnitude"))
    baseline = clean_text(parts.get("Baseline"))
    horizon = clean_text(parts.get("Target_Year_or_Period"))

    elements: list[str] = []

    # ---- 1. Horizon phrase ----
    if horizon:
        # Chinese FYP shorthand: 十三五, 十二五, 十四五, 十五五, etc.
        # Pattern: 十 + optional digit (一二…九) + 五
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
            # "2030年前" / "2030年左右" are already natural temporal phrases
            elements.append(horizon)
        elif re.match(r"\d{4}[-–]\d{4}", horizon):
            elements.append(f"{horizon}期间")
        elif horizon not in ("无", "N/A", ""):
            # Catch-all: use the horizon text as-is
            elements.append(horizon)

    # ---- 2. Baseline phrase ----
    # Skip baseline if the magnitude already contains a comparison
    # (e.g. "比2015年下降5%左右" already names the reference year)
    if baseline and baseline not in ("无", "N/A", "") and not _has_self_contained_comparison(
        magnitude
    ):
        if baseline.isdigit() and len(baseline) == 4:
            # Pure year → compact form: "较2020年"
            elements.append(f"较{baseline}年")
        else:
            # Descriptive baseline → "在{baseline}基础上"
            elements.append(f"在{baseline}基础上")

    # ---- 3. Target phrase (direction + magnitude) ----
    target = _build_target_phrase(direction, magnitude)
    if target:
        elements.append(target)

    if not elements:
        return "无"

    return "，".join(elements)
