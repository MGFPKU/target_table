from htmltools._core import Tag
from shiny import App, ui, reactive, render
import os
import polars as pl
import io
import requests

from table import output_paginated_table
from details import render_detail
from download import download_tab, send_to_email

# Dataset info ----
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "MGFPKU/target_table"
ASSET_NAME = "dataset.xlsx"


def fetch_data():
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


raw_df = fetch_data()
df = (
    raw_df.with_columns(
        pl.col(i18n("时间"))
        .str.strptime(pl.Date, "%m/%Y", strict=False)
        .alias("parsed_time")
    )
    .reverse()
    .sort("parsed_time", descending=True)
    .drop(["parsed_time", i18n("新闻链接"), i18n("备注")])
)

# fix region tags
regions: list[str] = df[i18n("经济体")].drop_nulls().to_list()
# Split by '；', strip whitespace, flatten
all_regions = sorted(
    set(r.strip() for entry in regions for r in entry.split(i18n("；")))
)

# compile ui
app_ui = ui.page_fluid(
    ui.navset_hidden(
        ui.nav_panel(
            "tabview",
            ui.layout_columns(
                ui.input_select(
                    "region",
                    i18n("经济体"),
                    choices=[i18n("全部")] + all_regions,
                ),
                ui.input_select(
                    "type",
                    i18n("政策类型"),
                    choices=[i18n("全部")]
                    + sorted(df[i18n("政策类型")].unique().to_list()),
                ),
                ui.input_select(
                    "year",
                    i18n("年份"),
                    choices=[i18n("全部")]
                    + sorted(
                        df[i18n("时间")].str.slice(3, 4).unique().to_list(),
                        reverse=True,
                    ),
                ),
                ui.input_text(
                    id="keyword", label=i18n("关键词"), placeholder=i18n("请输入关键词")
                ),
                ui.div(
                    ui.div(
                        "下载",
                        class_="form-label",
                        style="visibility: hidden; height: 1em;",
                    ),
                    ui.input_action_button(
                        "download",
                        "",
                        class_="download-icon",
                        icon=ui.tags.svg(
                            {
                                "xmlns": "http://www.w3.org/2000/svg",
                                "viewBox": "0 0 24 24",
                                "fill": "currentColor",
                                "height": "20",
                                "width": "20",
                            },
                            Tag(
                                "path",
                                d="M5 20h14v-2H5v2zm7-18v12l5-5h-3V4h-4v5H7l5 5V2z",
                            ),
                        ),
                    ),
                    class_="col-sm-2",  # mimic layout_columns spacing
                    style="display: flex; flex-direction: column; align-items: start; justify-content: end; padding-top: 0.6em;",
                ),
            ),
            ui.tags.style(f"""
                th, td {{
                    text-align: left;
                }}
                .download-icon {{
                    background-color: white;
                    border: 1px solid #ccc;
                    padding: 6px 12px;
                    border-radius: 8px;
                    cursor: pointer;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    transition: background-color 0.2s;
                    position: relative;
                }}
                .download-icon:hover {{
                    background-color: #f0f0f0;
                }}
                .download-icon:hover::after {{
                    content: '{i18n("下载结果")}';
                    position: absolute;
                    bottom: -2em;
                    background-color: #bbb;
                    color: black;
                    font-size: 12px;
                    padding: 4px 8px;
                    border-radius: 4px;
                    white-space: nowrap;
                }}

                .download-icon svg {{
                    width: 20px;
                    height: 20px;
                    fill: #333;
                }}
                
                .detail-buttons {{
                    display: flex;
                    gap: 1em;
                    margin-top: 1em;
                }}

                .detail-buttons a,
                .detail-buttons button {{
                    padding: 0.75em 2em;
                    font-size: 1em;
                    border: none;
                    border-radius: 999px;
                    cursor: pointer;
                    text-decoration: none;
                    color: white;
                    background-color: rgb(13, 97, 72);
                    transition: background-color 0.3s;
                }}

                .detail-buttons a:hover,
                .detail-buttons button:hover {{
                    color: white;
                    background-color: rgb(11, 82, 61);
                }}
            """),
            ui.navset_hidden(
                ui.nav_panel(
                    "table_panel",
                    ui.output_ui(id="table_ui"),
                ),
                download_tab,
                id="table_download",
            ),
        ),
        ui.nav_panel("detail_view", ui.output_ui("detail_ui")),
        id="view",
    )
)


def server(input, output, session):
    current_page = reactive.value(1)
    focused_policy = reactive.value(None)

    @reactive.Calc
    def filtered():
        current_page.set(1)
        data = df
        if input.region() != i18n("全部"):
            data = data.filter(pl.col(i18n("经济体")).str.contains(input.region()))
        if input.type() != i18n("全部"):
            data = data.filter(pl.col(i18n("政策类型")) == input.type())
        if input.year() != i18n("全部"):
            data = data.filter(
                pl.col(i18n("时间")).cast(str).str.slice(3, 4) == input.year()
            )
        if input.keyword():
            keyword: str = input.keyword().lower().strip()
            if keyword:
                string_cols = [
                    col for col, dtype in data.schema.items() if dtype == pl.String
                ]

                if string_cols:
                    filter_expr = pl.fold(
                        acc=pl.lit(False),
                        exprs=[
                            pl.col(col).str.to_lowercase().str.contains(keyword)
                            for col in string_cols
                        ],
                        function=lambda acc, expr: acc | expr,
                    )
                    data = data.filter(filter_expr)

        return data

    @output
    @render.ui  # table
    def table_ui():
        # Rearrange and format data
        data: pl.DataFrame = (
            filtered()
            .select(
                (
                    [
                        i18n("经济体"),
                        i18n("政策动态"),
                        i18n("政策类型"),
                        i18n("发布主体"),
                        i18n("时间"),
                    ]
                )
            )
            .with_columns(
                pl.col(i18n("时间"))
                .str.strptime(pl.Date, "%m/%Y", strict=False)
                .dt.strftime("%Y-%m")
            )
        )
        try:
            table: Tag = output_paginated_table("mytable", data, page=current_page())
            return table
        except Exception as e:
            print("⚠️ Error rendering table:", e)
            return ui.markdown(f"**Error rendering table:** `{e}`")

    @output
    @render.ui
    def detail_ui():
        if not focused_policy():
            return ui.markdown(i18n("⚠️ 未找到政策详情。"))
        row = df.filter(pl.col(i18n("政策动态")) == focused_policy())
        return render_detail(row)

    @reactive.effect
    @reactive.event(input.download)
    async def _():
        ui.update_navs("table_download", selected="download_panel")

    @render.text
    def nrow():
        return i18n("将通过邮件当前筛选结果，共 {} 条记录", filtered().shape[0])

    @reactive.effect
    @reactive.event(input.send_csv)
    async def _():
        data_csv: str = filtered().write_csv(
            include_bom=True,
            separator=",",
            quote_char='"',
            quote_style="non_numeric",
            null_value="",
        )  # Returns as string
        await send_to_email(input, session, "csv", data_csv)

    @reactive.effect
    @reactive.event(input.send_excel)
    async def _():
        # Step 1: Write Excel to in-memory buffer
        buffer = io.BytesIO()
        filtered().write_excel(buffer)
        buffer.seek(0)

        # Step 2: Send Excel to email
        await send_to_email(input, session, "xlsx", buffer.getvalue())

    @reactive.Effect
    def on_click():
        if input.mytable():
            focused_policy.set(input.mytable())
            ui.update_navs("view", selected="detail_view")

    @reactive.effect
    @reactive.event(input.mytable_page)
    async def _():
        current_page.set(input.mytable_page())

    @reactive.effect
    @reactive.event(input.back)
    async def _():
        ui.update_navs("view", selected="tabview")

    @reactive.effect
    @reactive.event(input.back1)
    async def _():
        ui.update_navs("table_download", selected="table_panel")


app = App(app_ui, server, debug=False)
