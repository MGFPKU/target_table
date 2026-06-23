# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development commands

```bash
uv sync                          # Install dependencies
python -m shiny run --reload app.py  # Run dev server at http://localhost:8000
```

There are no tests or linting configured (`uv` with pyproject.toml, no pytest/ruff).

## Architecture

This is a **Shiny for Python** app that displays China's national climate policy targets in a paginated, filterable table. The live app fetches its dataset from GitHub Releases on every cold start; a `LOCAL_DATA=TRUE` env var switches it to a local file for development.

**Data flow:**
1. `fetch_raw_data()` in `data.py` downloads `dataset.xlsx` from the latest GitHub release of `MGFPKU/target_dataset` (or reads a local file).
2. `get_data()` loads each sheet listed in `sheets.json`, merges them with Polars, applies `clean_text` + `format_target` from `target_format.py` to build the `Target` display column, and sorts the merged DataFrame.
3. `app.py` holds the Shiny UI (`app_ui`) and server function. Filters on target horizon, category, and keyword produce a `filtered()` reactive calc; the table output delegates to `output_paginated_table()`.
4. `table.py` renders an HTML table with manual pagination controls (buttons + dropdown). Rows share a `rowspan` on the `Metric` column for consecutive identical metrics. Clicking a row fires a Shiny input event.
5. `download.py` handles the email export tab: it POSTs base64-encoded XLSX to a Google Apps Script endpoint, which forwards the file by email.

**i18n:** `i18n.py` reads `LANGUAGE` (CN/EN) — CN returns keys verbatim, EN looks them up in `translation.json`. The `i18n()` function supports `str.format` placeholders.

**Key dependencies:** `shiny`, `polars`, `fastexcel` (fast Excel reading), `xlsxwriter`, `httpx`.

## Environment variables

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | PAT with read access to `MGFPKU/target_dataset` |
| `GOOGLE_SCRIPT_URL` | Google Apps Script web app for email delivery |
| `LANGUAGE` | `CN` (default) or `EN` |
| `LOCAL_DATA` | Set to `TRUE` to load a local Excel file instead of GitHub |

## Column display pipeline

`WANTED_COLS` in `data.py` defines the columns pulled from each sheet. `DISPLAY_COLS` (Metric, Announced, Target, Target_Category) defines what the user sees. The `Target` column is synthesized at load time from four source fields (`Direction`, `Target_Magnitude`, `Baseline`, `Target_Year_or_Period`) via `format_target()` — this handles FYP ordinal expansion, "by YYYY" / "during period" phrasing, and magnitude-baseline concatenation.

## Sheets configuration

`sheets.json` lists the source sheets inside `dataset.xlsx` that are read and concatenated. The "Energy|Power" entry covers two identically-structured sheets that `pl.read_excel` treats as a single sheet name.
