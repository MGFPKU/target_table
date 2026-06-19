import os, io
import requests
import polars as pl
import json
import re

# Dataset info ----
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "MGFPKU/target_dataset"
ASSET_NAME = "dataset.xlsx"
LOCAL_DATA: bool = os.getenv("LOCAL_DATA", "FALSE").upper() == "TRUE"
LANGUAGE: str = os.getenv("LANGUAGE", "CN").upper()

DISPLAY_COLS = [
    "Metric",
    "Announced",
    "Target",
    "Target_Category",
]

WANTED_COLS = [
    "Announcement_Year",
    "Metric",
    "Direction",
    "Target_Magnitude",
    "Baseline",
    "Target_Year_or_Period",
    "Target_Category",
    "Accountability",
    "Sentence",
    "Document",
    "Topic_Label",
]

def get_fyp_year_range(ordinal_str: str) -> str | None:
    """Compute the year range for a given FYP ordinal (e.g., "10th" → "2001-2005").

    The 10th FYP spans 2001–2005; each subsequent plan shifts forward by 5 years.
    """
    match = re.fullmatch(r"(\d+)(?:st|nd|rd|th)", ordinal_str)
    if not match:
        return None
    n = int(match.group(1))
    start_year = 2001 + (n - 10) * 5
    return f"{start_year}-{start_year + 4}"


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.strip().upper() in {"", "N/A", "NA", "NONE", "NULL"}:
        return ""
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def format_target(parts: dict[str, object]) -> str:
    direction = clean_text(parts.get("Direction"))
    magnitude = clean_text(parts.get("Target_Magnitude"))
    baseline = clean_text(parts.get("Baseline"))
    horizon = clean_text(parts.get("Target_Year_or_Period"))

    target_phrase = " ".join(part for part in [direction, magnitude] if part)
    if baseline:
        target_phrase = f"{target_phrase} from {baseline} levels" if target_phrase else f"from {baseline} levels"

    if horizon:
        fyp_match = re.fullmatch(r"(the\s+)?(?P<ordinal>\d+(?:st|nd|rd|th))\s+FYP", horizon, flags=re.IGNORECASE)
        if fyp_match:
            ordinal = fyp_match.group("ordinal")
            year_range = get_fyp_year_range(ordinal.lower())
            period = f"the {ordinal} FYP"
            if year_range:
                period = f"{period} ({year_range})"
            prefix = f"during {period}"
        elif re.fullmatch(r"\d{4}", horizon):
            prefix = f"by {horizon}"
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


def fetch_raw_data() -> io.BytesIO:
    if LOCAL_DATA:
        with open("../CHINA'S NATIONAL CLIMATE TARGETS DATABASE.xlsx", "rb") as f:
            print("Using local data...")
            return io.BytesIO(f.read())
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    # 1️⃣ Get latest release metadata
    latest_url = f"https://api.github.com/repos/{REPO}/releases/latest"
    res = requests.get(latest_url, headers=headers)

    if res.status_code != 200:
        raise RuntimeError(f"Failed to fetch file: {res.status_code}\n{res.text}")

    release = res.json()

    # 2️⃣ Find the asset
    asset = next((a for a in release["assets"] if a["name"] == ASSET_NAME), None)

    if asset is None:
        raise RuntimeError("dataset.xlsx not found in latest release.")

    asset_id = asset["id"]

    # 3️⃣ Download asset binary
    download_headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/octet-stream",
    }

    download_url = f"https://api.github.com/repos/{REPO}/releases/assets/{asset_id}"
    file_res = requests.get(download_url, headers=download_headers)

    if file_res.status_code != 200:
        raise RuntimeError(f"Failed to download file:\n{file_res.text}")

    # 4️⃣ Load Excel into Polars
    return io.BytesIO(file_res.content)


def get_sheet_names() -> list[str]:
    with open("sheets.json", "r", encoding="utf-8") as f:
        dicts: dict = json.load(f)
    sheet_names: list[str] = dicts.get("sheets", [])[0]
    if not sheet_names:
        raise RuntimeError("No sheet names found in sheets.json")
    return sheet_names


def get_data() -> pl.DataFrame:

    raw_xlsx = fetch_raw_data()

    sheet_names = get_sheet_names()
    combined_sheet: pl.DataFrame | None = None

    for sheet_name in sheet_names:
        raw_xlsx.seek(0)
        sheet = (
            pl.read_excel(raw_xlsx, sheet_name=sheet_name)
            .with_columns(pl.all().cast(pl.Utf8))
            .filter(pl.col("Count") != "r")
        )
        available_cols = [col for col in WANTED_COLS if col in sheet.columns]
        missing_cols = [col for col in WANTED_COLS if col not in sheet.columns]
        if missing_cols:
            raise RuntimeError(
                f"Sheet '{sheet_name}' is missing required columns: {', '.join(missing_cols)}"
            )

        sheet = sheet.select(available_cols).with_columns(
            pl.col("Announcement_Year").alias("Announced"),
            pl.col("Metric")
            .map_elements(clean_text, return_dtype=pl.Utf8)
            .alias("Metric"),
            pl.struct(
                "Direction",
                "Target_Magnitude",
                "Baseline",
                "Target_Year_or_Period",
            )
            .map_elements(format_target, return_dtype=pl.Utf8)
            .alias("Target"),
        )
        combined_sheet = (
            sheet if combined_sheet is None else pl.concat([combined_sheet, sheet])
        )

    if combined_sheet is None:
        raise RuntimeError(
            "No sheets were processed. Check sheets.json and dataset.xlsx"
        )

    return (
        combined_sheet.fill_null("N/A")
        .with_columns(
            pl.col("Target_Year_or_Period")
            .str.extract(r"(\d{4})")
            .cast(pl.Int32, strict=False)
            .alias("_sort_target_year"),
            pl.col("Metric").alias("_sort_metric"),
        )
        .sort(
            by=[
                "_sort_metric",
                "Announced",
                "Target_Category",
                "_sort_target_year",
                "Target_Year_or_Period",
                "Target",
            ],
            descending=[False, False, False, False, False, False],
            nulls_last=True,
        )
        .drop(["_sort_target_year", "_sort_metric"])
    )
