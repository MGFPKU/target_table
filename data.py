import os, io
import requests
import polars as pl
import json

# Dataset info ----
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "MGFPKU/target_table"
ASSET_NAME = "dataset.xlsx"

WANTED_COLS = [
    "Metric",
    "Direction",
    "Target_Magnitude",
    "Baseline_Year",
    "Target_Year_or_Period",
    "Target_Category",
    "Document",
]


def promote_second_row_to_header(df: pl.DataFrame) -> pl.DataFrame:
    """Use the first row of `df` as column names and drop that row.

    Polars by default uses the first Excel row as column names. If the actual
    headers live in the second Excel row (which becomes the first row of the
    DataFrame), promote that row to be the DataFrame columns and remove it.
    """
    if df.height == 0:
        return df
    header_vals = [str(v) if v is not None else "" for v in df.row(0)]
    df = df.slice(1)
    df.columns = header_vals
    return df


def fetch_raw_data() -> io.BytesIO:
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


def get_sheet_names() -> tuple[list[str], str]:
    with open("sheets.json", "r", encoding="utf-8") as f:
        dicts: dict = json.load(f)
    sheet_names: list[str] = dicts.get("sheets", [])[0]
    if not sheet_names:
        raise RuntimeError("No sheet names found in sheets.json")
    source_sheet: str = dicts.get("source", "")
    if source_sheet == "":
        raise RuntimeError("No source sheet specified in sheets.json")
    return sheet_names, source_sheet


def get_data() -> pl.DataFrame:

    raw_xlsx = fetch_raw_data()

    sheet_names, source_sheet = get_sheet_names()
    source_sheet = pl.read_excel(raw_xlsx, sheet_name=source_sheet)
    source_sheet = promote_second_row_to_header(source_sheet).select(
        ["code", "doc_name_en", "doc_name_zh"]
    )

    combined_sheet = None
    for sheet_name in sheet_names:
        sheet = pl.read_excel(raw_xlsx, sheet_name=sheet_name)
        sheet = sheet.with_columns(
            pl.col("Document").str.replace(r"\.[^.]+$", "").alias("Document")
        )
        sheet = sheet.select(WANTED_COLS)
        sheet = sheet.join(
            source_sheet, left_on="Document", right_on="code", how="left"
        )
        combined_sheet: pl.DataFrame = sheet if combined_sheet is None else pl.concat([combined_sheet, sheet])


    if combined_sheet is None:
        return pl.DataFrame()

    return combined_sheet
