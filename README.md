# 📊 MGF Dataset Explorer (Shiny App)

An interactive **Shiny for Python** web app for browsing and analyzing climate-related policy actions by central banks and financial regulators — developed by the **Macro and Green Finance Lab at Peking University (MGF@PKU)**.

This tool is designed as a **template** for research, presentation, and educational purposes. It is not intended for local hosting by the general public — instead, it showcases how one might integrate real-time GitHub-hosted datasets into a Shiny app.

<img src="https://github.com/user-attachments/assets/4d1eb867-3455-497f-8f63-93e40c1c4d08" width="800"/>

---

## 🔍 Overview

This app visualizes a curated dataset of climate and sustainability-related regulatory measures from **major economies (G20, EU, etc.) since 2021**. Features include:

- 🔎 Filtering by region, policy type, year, and keyword
- 🧾 Structured detail view for each policy
- 🔗 Links to original sources
- 📥 Export of filtered results (CSV)

Powered by:

- [`shiny`](https://shiny.posit.co/py/) for interactivity
- [`polars`](https://pola.rs/) for fast data wrangling
- GitHub API for real-time data retrieval
- Custom CSS + JS enhancements

---

## 📦 Features

- Paginated and stylized data table
- Clickable rows with detailed policy views
- CSV export of current filtered results
- Integrated GitHub data sync (via authenticated API)
- Modern UI with iconography, tooltips, and layout styling

---

## 🧪 Setup (For Contributors Only)

This app uses GitHub as a remote data backend. If you're customizing or extending the app:

### 1. Clone the repo

```bash
git clone https://github.com/MGFPKU/MGF_dataset_shiny.git
cd MGF_dataset_shiny
```

### 2. Install dependencies

We use `uv` for fast dependency resolution:

```bash
uv sync
```

### 3. Set up environment variables

> ⚠️ We do not publish a GitHub token in this repo.
> If you need access for development or testing, contact the maintainers for a personal access token (PAT) with read-only access to the dataset repository.

You’ll need to set the token in a `.env` file like:

```env
GITHUB_TOKEN=ghp_...
GOOGLE_SCRIPT_URL=https://script.google.com/macros/s/...
LANGUAGE=EN
```

Below is what each variable does:

- `GITHUB_TOKEN`: a GitHub Personal Access Token (PAT) with read access to the dataset repository. The app uses this token when calling the GitHub API to fetch `data/data.csv`. Keep this token private (do not commit it).
- `GOOGLE_SCRIPT_URL`: the public URL for a Google Apps Script web app that acts as the mailing bot. The Shiny app POSTs filtered exports (CSV/XLSX) to this endpoint and the script forwards them by email.
- `LANGUAGE`: set the UI language for the app. Use `EN` for English or `CN` for Chinese. The value controls which translations are displayed in the interface.

### 4. Run the app

```bash
python -m shiny run --reload  app.py
```

Then open your browser to:

```bash
http://localhost:8000
```

Or more conveniently, install the `shiny` extension to Positron/VS Code and press the Run button.

---

## 📁 Project structure

The repository layout and purpose of key files:

```
.env                  # Environment variables (not committed, create locally following setup instructions)
app.py                # Main Shiny app (UI + server)
details.py            # Renders detailed policy view
table.py              # Paginated table output and helpers
download.py           # Download UI and mailing helpers (POSTs to Google Script)
i18n.py               # Translation helper; reads LANGUAGE to switch UI
translation.json      # Translation strings used by `i18n.py`
pyproject.toml        # Project metadata / build config (managed by uv)
.python-version       # Python version pinning for uv
requirements.txt      # Dependency pins (optional with pyproject)
LICENSE               # License
README.md             # Project documentation (this file)
.gitignore            # Git ignore rules
```

Notes:
- Edit `app.py` to change high-level UI or filtering logic.
- `table.py` and `details.py` control how policy rows and detail pages are rendered.
- `download.py` integrates with the Google Apps Script mailing bot (set via `GOOGLE_SCRIPT_URL`).


## 📚 Citation

If you use the MGF dataset in your research or writing, please cite us as follows:

**Macro and Green Finance Lab, Peking University (MGF@PKU)**  
"Climate-related Policy Tracker for Central Banks and Regulators"  
[https://mgflab.nsd.pku.edu.cn/MGFsjk/zczz/index.htm](https://mgflab.nsd.pku.edu.cn/MGFsjk/zczz/index.htm), 2025.

<!-- > For formal citation formats (APA, BibTeX, etc.), see the linked page above. -->

---

## 📁 Data Source

The dataset is hosted in a _private_ GitHub repository along with our scraping scripts. We apologize for the inconvenience. But the dataset provided through the app is updated in real-time and contains most information available on the original source.

---

## 🏛️ Credits

Developed by Dianyi Yang ([@kv9898](https://github.com/kv9898)) for the **[Macro and Green Finance Lab](https://mgflab.nsd.pku.edu.cn/en/AboutUs/OurTeam/index.htm)** at Peking University (MGF@PKU).

If you use or adapt this project for academic or institutional purposes, please **cite the dataset** accordingly and feel free to **reach out for collaboration or inquiries**.
