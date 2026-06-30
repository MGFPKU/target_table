import os, io
import requests
import polars as pl
import json

from target_format import clean_text, format_target, format_target_cn

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

# Chinese local file support ------------------------------------------------
CN_LOCAL_FILE = "../中国国家气候目标数据库.xlsx"
CN_COLUMN_MAP: dict[str, str] = {
    "公布年份": "Announcement_Year",
    "指标": "Metric",
    "方向": "Direction",
    "目标值": "Target_Magnitude",
    "基线": "Baseline",
    "目标年份/时期": "Target_Year_or_Period",
    "计数": "Count",
    "目标类别": "Target_Category",
    "责任主体": "Accountability",
    "政策原文": "Sentence",
    "文件": "Document",
    "主题标签": "Topic_Label",
}
# Map internal English column name → Chinese display label
CN_HEADER_MAP: dict[str, str] = {
    "Metric": "指标",
    "Announced": "公布年份",
    "Target": "目标",
    "Target_Category": "目标类别",
}


def fetch_raw_data() -> io.BytesIO:
    if LOCAL_DATA:
        if LANGUAGE == "CN":
            file_path = CN_LOCAL_FILE
        else:
            file_path = "../CHINA'S NATIONAL CLIMATE TARGETS DATABASE.xlsx"
        with open(file_path, "rb") as f:
            print(f"Using local data ({file_path})...")
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
        data: dict = json.load(f)
    sheets = data.get("sheets", {})
    # Support both nested {CN: [...], EN: [...]} and legacy [[...]] formats
    if isinstance(sheets, dict):
        sheet_names: list[str] = sheets.get(LANGUAGE, sheets.get("EN", []))
    else:
        # Legacy format: sheets is a list of lists
        sheet_names: list[str] = sheets[0] if sheets else []
    if not sheet_names:
        raise RuntimeError("No sheet names found in sheets.json")
    return sheet_names


def _rename_cn_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Rename Chinese source column names to internal English names."""
    rename_map = {cn: en for cn, en in CN_COLUMN_MAP.items() if cn in df.columns}
    return df.rename(rename_map)


def _load_cn_data(raw_xlsx: io.BytesIO) -> pl.DataFrame:
    """Load and process data from the Chinese Excel file.

    Differences from get_data():
      - Chinese source column names are renamed to internal English names
      - No Count != "r" filter (Chinese data has no reference rows)
      - Uses format_target_cn() for Chinese target display
      - Uses fill_null("无") instead of fill_null("N/A")
    """
    sheet_names = get_sheet_names()
    combined_sheet: pl.DataFrame | None = None

    for sheet_name in sheet_names:
        raw_xlsx.seek(0)
        sheet = (
            pl.read_excel(raw_xlsx, sheet_name=sheet_name)
            .with_columns(pl.all().cast(pl.Utf8))
        )
        # Rename Chinese columns → internal English names
        sheet = _rename_cn_columns(sheet)

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
            .map_elements(format_target_cn, return_dtype=pl.Utf8)
            .alias("Target"),
        )
        combined_sheet = (
            sheet if combined_sheet is None else pl.concat([combined_sheet, sheet])
        )

    if combined_sheet is None:
        raise RuntimeError(
            "No sheets were processed. Check the Chinese Excel file."
        )

    return (
        combined_sheet.fill_null("无")
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


def get_data() -> pl.DataFrame:

    raw_xlsx = fetch_raw_data()

    if LANGUAGE == "CN" and LOCAL_DATA:
        return _load_cn_data(raw_xlsx)

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
