import os, io
import requests
import polars as pl
import json

from target_format import clean_text, format_target, format_target_cn

# Dataset info ----
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "MGFPKU/target_dataset"
LOCAL_DATA: bool = os.getenv("LOCAL_DATA", "FALSE").upper() == "TRUE"

# GitHub release asset name per language
_ASSET_NAME = {"CN": "Chinese.xlsx", "EN": "English.xlsx"}

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

# Chinese source column name → internal English name
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

# Reverse: internal English name → Chinese source name
_EN_TO_CN = {en: cn for cn, en in CN_COLUMN_MAP.items()}

# Chinese display labels for DISPLAY_COLS.
# Derived from _EN_TO_CN; "Announced" is aliased from Announcement_Year at
# load time, and "Target" is a computed column with no source equivalent.
CN_HEADER_MAP: dict[str, str] = {
    col: "目标" if col == "Target"
    else _EN_TO_CN.get("Announcement_Year" if col == "Announced" else col, col)
    for col in DISPLAY_COLS
}

# Per-language data cache — loaded once on first request per language
_data_cache: dict[str, pl.DataFrame] = {}


def _resolve_lang(lang: str | None) -> str:
    """Normalise a language string to CN or EN, falling back to env var."""
    if lang is None:
        lang = os.getenv("LANGUAGE", "CN")
    lang = lang.upper()
    if lang not in ("CN", "EN"):
        lang = "CN"
    return lang


def fetch_raw_data(lang: str | None = None) -> io.BytesIO:
    lang = _resolve_lang(lang)
    if LOCAL_DATA:
        if lang == "CN":
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

    # 2️⃣ Find the language-appropriate asset
    asset_name = _ASSET_NAME.get(lang, _ASSET_NAME["CN"])
    asset = next((a for a in release["assets"] if a["name"] == asset_name), None)

    if asset is None:
        raise RuntimeError(f"{asset_name} not found in latest release.")

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


def get_sheet_names(lang: str | None = None) -> list[str]:
    lang = _resolve_lang(lang)
    with open("sheets.json", "r", encoding="utf-8") as f:
        data: dict = json.load(f)
    sheets = data.get("sheets", {})
    # Support both nested {CN: [...], EN: [...]} and legacy [[...]] formats
    if isinstance(sheets, dict):
        sheet_names: list[str] = sheets.get(lang, sheets.get("CN", []))
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


def _build_doc_title_map(raw_xlsx: io.BytesIO, lang: str) -> dict[str, str]:
    """Read the Sources sheet and return a mapping from document code → title.

    The Sources sheet (``来源`` / ``Sources``) has multi-row headers and
    interspersed category-label rows.  We locate the real header row (col 0
    is ``编号`` or ``code``), then gather every data row whose first column
    looks like a document code (e.g. ``HL2104``).

    Returns a dict mapping the code to the document title in the current
    language.
    """
    import re

    sheet_name = "来源" if lang == "CN" else "Sources"
    raw_xlsx.seek(0)
    src = pl.read_excel(raw_xlsx, sheet_name=sheet_name, has_header=False)

    # Find the header row — the row whose first cell is "编号" or "code"
    header_row_idx: int | None = None
    for i in range(len(src)):
        cell = str(src.row(i)[0])
        if cell in ("编号", "code"):
            header_row_idx = i
            break

    if header_row_idx is None:
        raise RuntimeError(
            f"Could not find header row in '{sheet_name}' sheet"
        )

    # Build the mapping: row is data if col 0 looks like a doc code
    code_re = re.compile(r"^[A-Z]+\d+")
    doc_map: dict[str, str] = {}
    for i in range(header_row_idx + 1, len(src)):
        row = src.row(i)
        code = str(row[0]) if row[0] is not None else ""
        if not code_re.match(code):
            continue  # category label, blank, or other non-data row

        # Pick the title column for the current language
        title = row[2]  # Chinese title
        if lang == "EN":
            title = row[3]  # English title

        if title is not None and str(title).strip():
            doc_map[code] = str(title).strip()

    return doc_map


def _load_cn_data(raw_xlsx: io.BytesIO, lang: str) -> pl.DataFrame:
    """Load and process data from the Chinese Excel file.

    Differences from _load_en_data():
      - Chinese source column names are renamed to internal English names
      - Filters Count != "重申目标" (equivalent to English Count != "r")
      - Uses format_target_cn() for Chinese target display
      - Uses fill_null("无") instead of fill_null("N/A")
    """
    sheet_names = get_sheet_names(lang)
    combined_sheet: pl.DataFrame | None = None

    for sheet_name in sheet_names:
        raw_xlsx.seek(0)
        sheet = (
            pl.read_excel(raw_xlsx, sheet_name=sheet_name)
            .with_columns(pl.all().cast(pl.Utf8))
        )
        # Rename Chinese columns → internal English names
        sheet = _rename_cn_columns(sheet).filter(
            pl.col("Count") != "重申目标"
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

    # Build document-code → title lookup from the Sources sheet
    doc_map = _build_doc_title_map(raw_xlsx, lang)

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
                "Target_Category",
                "_sort_metric",
                "Announced",
                "_sort_target_year",
                "Target_Year_or_Period",
                "Target",
            ],
            descending=[False, False, False, False, False, False],
            nulls_last=True,
        )
        .drop(["_sort_target_year", "_sort_metric"])
        .with_columns(
            pl.col("Document")
            .str.replace(r"\.(pdf|htm|html|docx?|PDF|HTM|HTML|DOCX?)$", "")
            .map_elements(
                lambda code: f"来源：{doc_map[code]}" if code in doc_map else None,
                return_dtype=pl.Utf8,
            )
            .alias("Doc_Title"),
        )
    )


def _load_en_data(raw_xlsx: io.BytesIO, lang: str) -> pl.DataFrame:
    """Load and process data from the English Excel file."""
    sheet_names = get_sheet_names(lang)
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
                "Announcement_Year",
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

    # Build document-code → title lookup from the Sources sheet
    doc_map = _build_doc_title_map(raw_xlsx, lang)

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
                "Target_Category",
                "_sort_metric",
                "Announced",
                "_sort_target_year",
                "Target_Year_or_Period",
                "Target",
            ],
            descending=[False, False, False, False, False, False],
            nulls_last=True,
        )
        .drop(["_sort_target_year", "_sort_metric"])
        .with_columns(
            pl.col("Document")
            .str.replace(r"\.(pdf|htm|html|docx?|PDF|HTM|HTML|DOCX?)$", "")
            .map_elements(
                lambda code: f"Source: {doc_map[code]}" if code in doc_map else None,
                return_dtype=pl.Utf8,
            )
            .alias("Doc_Title"),
        )
    )


def get_data(lang: str | None = None) -> pl.DataFrame:
    """Return the full dataset for *lang*, caching it in memory.

    Call this from inside a Shiny session so ``lang`` can be driven by a
    query parameter (``?lang=cn`` / ``?lang=en``).  The first call per
    language fetches and processes the Excel file; subsequent calls hit an
    in-memory cache.
    """
    lang = _resolve_lang(lang)

    if lang in _data_cache:
        return _data_cache[lang]

    raw_xlsx = fetch_raw_data(lang)
    if lang == "CN":
        df = _load_cn_data(raw_xlsx, lang)
    else:
        df = _load_en_data(raw_xlsx, lang)

    _data_cache[lang] = df
    return df
