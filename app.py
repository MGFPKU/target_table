import os
from htmltools._core import Tag
from shiny import App, ui, reactive, render

import polars as pl
import io

from table import output_paginated_table
from download import download_tab, send_to_email
from data import DISPLAY_COLS, get_data, fetch_raw_data, CN_HEADER_MAP
from i18n import i18n, get_lang, set_language


def display_data(data: pl.DataFrame) -> pl.DataFrame:
    df = data.select(DISPLAY_COLS)
    if get_lang() == "CN":
        df = df.rename(CN_HEADER_MAP)
    return df


# Static CSS (no i18n calls that need per-session switching)
_static_styles = ui.tags.style("""
    th, td {
        text-align: left;
    }
    .download-icon {
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
    }
    .download-icon:hover {
        background-color: #f0f0f0;
    }
    .download-icon:hover::after {
        position: absolute;
        bottom: -2em;
        background-color: #bbb;
        color: black;
        font-size: 12px;
        padding: 4px 8px;
        border-radius: 4px;
        white-space: nowrap;
    }

    .download-icon svg {
        width: 20px;
        height: 20px;
        fill: #333;
    }

    .detail-buttons {
        display: flex;
        gap: 1em;
        margin-top: 1em;
    }

    .detail-buttons a,
    .detail-buttons button {
        padding: 0.75em 2em;
        font-size: 1em;
        border: none;
        border-radius: 999px;
        cursor: pointer;
        text-decoration: none;
        color: white;
        background-color: rgb(13, 97, 72);
        transition: background-color 0.3s;
    }

    .detail-buttons a:hover,
    .detail-buttons button:hover {
        color: white;
        background-color: rgb(11, 82, 61);
    }
""")

# Minimal top-level UI — the labelled UI is built reactively in server()
app_ui = ui.page_fluid(
    _static_styles,
    ui.output_ui("table_download_navs"),
)


def server(input, output, session):

    @reactive.calc
    def lang():
        query = session.clientdata.url_search()
        params = {}
        if query.startswith("?"):
            query = query[1:]
        for pair in query.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k] = v
        # Query param takes precedence; fall back to env var; ultimate default CN
        return params.get("lang") or os.getenv("LANGUAGE", "CN")

    @reactive.calc
    def df():
        """Load the language-appropriate dataset (cached per language)."""
        return get_data(lang())

    @render.ui
    def table_download_navs():
        set_language(lang())

        # Per-session CSS that uses i18n (tooltip text)
        per_session_styles = ui.tags.style(f"""
            .download-icon:hover::after {{
                content: '{i18n("下载结果")}';
            }}
        """)

        data = df()

        filter_bar = ui.layout_columns(
            ui.input_select(
                "target_horizon",
                i18n("目标时间"),
                choices=[i18n("全部")]
                + sorted(data["Target_Year_or_Period"].unique().to_list()),
            ),
            ui.input_select(
                "target_category",
                i18n("目标类型"),
                choices=[i18n("全部")]
                + sorted(
                    data["Target_Category"].unique().to_list()
                ),
            ),
            ui.input_text(
                id="keyword", label=i18n("关键词"), placeholder=i18n("请输入关键词")
            ),
            ui.div(
                ui.div(
                    "下载",
                    class_="form-label",
                    style="visibility: hidden;",
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
                class_="col-sm-2",
                style="display: flex; flex-direction: column; align-items: start; justify-content: end;",
            ),
        )

        return ui.navset_hidden(
            ui.nav_panel(
                "tabview",
                per_session_styles,
                filter_bar,
                ui.navset_hidden(
                    ui.nav_panel(
                        "table_panel",
                        ui.output_ui(id="table_ui"),
                    ),
                    download_tab(),
                    id="table_download",
                ),
            ),
            id="view",
        )

    current_page = reactive.value(1)
    focused_policy = reactive.value(None)

    @reactive.Calc
    def filtered():
        set_language(lang())
        current_page.set(1)
        data = df()
        if input.target_horizon() != i18n("全部"):
            data = data.filter(pl.col("Target_Year_or_Period") == input.target_horizon())
        if input.target_category() != i18n("全部"):
            data = data.filter(
                pl.col("Target_Category") == input.target_category()
            )
        if input.keyword():
            keyword: str = input.keyword().lower().strip()
            if keyword:
                string_cols = ["Metric", "Target"]

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
        set_language(lang())
        data: pl.DataFrame = filtered()
        try:
            table: Tag = output_paginated_table(
                "mytable", data, page=current_page(),
                display_columns=DISPLAY_COLS, tooltip_col="Doc_Title",
            )
            return table
        except Exception as e:
            print("⚠️ Error rendering table:", e)
            return ui.markdown(f"**Error rendering table:** `{e}`")

    @reactive.effect
    @reactive.event(input.download)
    async def _():
        ui.update_navs("table_download", selected="download_panel")

    @render.text
    def nrow():
        set_language(lang())
        return i18n("将通过邮件当前筛选结果，共 {} 条记录", filtered().shape[0])

    @reactive.effect
    @reactive.event(input.send_all)
    async def _():
        raw_data = fetch_raw_data(lang())
        await send_to_email(input, session, "xlsx", raw_data.getvalue())

    @reactive.effect
    @reactive.event(input.send_selected)
    async def _():
        set_language(lang())
        # Step 1: Write Excel to in-memory buffer
        buffer = io.BytesIO()
        display_data(filtered()).write_excel(buffer)
        buffer.seek(0)

        # Step 2: Send Excel to email
        await send_to_email(input, session, "xlsx", buffer.getvalue())

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
