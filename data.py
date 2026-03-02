import os, io
import requests
import polars as pl
import json

# Dataset info ----
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "MGFPKU/target_table"
ASSET_NAME = "dataset.xlsx"


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
    with open('sheets.json', 'r', encoding='utf-8') as f:
        dicts: dict = json.load(f)
    sheet_names: list[str] = dicts.get("sheets", [])[0]
    if not sheet_names:
        raise RuntimeError("No sheet names found in sheets.json")
    source_sheet: str = dicts.get("source", "")
    if source_sheet == "":
        raise RuntimeError("No source sheet specified in sheets.json")
    return sheet_names, source_sheet

def get_data() -> pl.DataFrame:

    sheet_names, source_sheet = get_sheet_names()

    raw_xlsx = fetch_raw_data()
    dfs = pl.read_excel(raw_xlsx, sheet_name=None)
    return dfs["Sheet1"]