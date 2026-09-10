import os
from htmltools._core import Tag
from shiny import App, ui, reactive, render

import polars as pl
import io

from table import output_paginated_table
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
        display: block;
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
                content: '{i18n("下载筛选结果或完整数据集")}';
            }}
        """)

        data = df()

        filter_bar = ui.layout_columns(
            ui.input_selectize(
                "target_horizon",
                i18n("目标时间"),
                multiple=True,
                choices=sorted(data["Target_Year_or_Period"].unique().to_list()),
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
                ui.download_button(
                    "download_data",
                    ui.tags.svg(
                        {
                            "xmlns": "http://www.w3.org/2000/svg",
                            "viewBox": "0 0 24 24",
                            "fill": "currentColor",
                            "height": "20",
                            "width": "20",
                            "aria-hidden": "true",
                        },
                        Tag(
                            "path",
                            d="M5 20h14v-2H5v2zm7-18v12l5-5h-3V4h-4v5H7l5 5V2z",
                        ),
                    ),
                    class_="download-icon",
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
                ui.div(
                    i18n("💡 悬停行上可查看来源文件"),
                    style="font-size: 0.85em; color: #888; margin-top: 0.5em; margin-bottom: 0.5em;",
                ),
                ui.output_ui(id="table_ui"),
            ),
            id="view",
        )

    current_page = reactive.value(1)
    focused_policy = reactive.value(None)
    last_horizon_update = reactive.value(None)
    last_category_update = reactive.value(None)

    @reactive.effect
    def _sync_target_horizon_choices():
        """Limit target horizons to those available for the selected category."""
        set_language(lang())
        all_label = i18n("全部")
        selected_category = input.target_category()
        if selected_category is None:
            return

        data = df()
        if selected_category != all_label:
            data = data.filter(
                pl.col("Target_Category") == selected_category
            )

        choices = sorted(
            data["Target_Year_or_Period"].unique().to_list()
        )
        with reactive.isolate():
            current_selection = input.target_horizon() or ()
            previous_update = last_horizon_update()
        selected = [value for value in current_selection if value in choices]
        update = (tuple(choices), tuple(selected))

        if update != previous_update:
            last_horizon_update.set(update)
            ui.update_selectize(
                "target_horizon",
                choices=choices,
                selected=selected,
            )

    @reactive.effect
    def _sync_target_category_choices():
        """Limit target categories to those available for selected horizons."""
        set_language(lang())
        selected_horizons = input.target_horizon()
        if selected_horizons is None:
            return

        data = df()
        if selected_horizons:
            data = data.filter(
                pl.col("Target_Year_or_Period").is_in(selected_horizons)
            )

        all_label = i18n("全部")
        available_categories = sorted(
            data["Target_Category"].unique().to_list()
        )
        choices = [all_label, *available_categories]
        with reactive.isolate():
            current_selection = input.target_category()
            previous_update = last_category_update()
        selected = (
            current_selection
            if current_selection in available_categories
            else all_label
        )
        update = (tuple(choices), selected)

        if update != previous_update:
            last_category_update.set(update)
            ui.update_select(
                "target_category",
                choices=choices,
                selected=selected,
            )

    def _apply_filters(data: pl.DataFrame) -> pl.DataFrame:
        if input.target_horizon():
            data = data.filter(
                pl.col("Target_Year_or_Period").is_in(input.target_horizon())
            )
        if input.target_category() != i18n("全部"):
            data = data.filter(
                pl.col("Target_Category") == input.target_category()
            )
        keyword: str = (input.keyword() or "").lower().strip()
        if keyword:
            string_cols = ["Metric", "Target"]
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

    @reactive.Calc
    def filtered():
        set_language(lang())
        current_page.set(1)
        return _apply_filters(df())

    @reactive.calc
    def has_filters() -> bool:
        set_language(lang())
        if input.target_horizon():
            return True
        if input.target_category() != i18n("全部"):
            return True
        return bool((input.keyword() or "").strip())

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
            return ui.div(
                ui.div(
                    i18n("共 {} 条记录", data.height),
                    style="color: #666; margin: 0.5em 0;",
                ),
                table,
            )
        except Exception as e:
            print("⚠️ Error rendering table:", e)
            return ui.markdown(f"**Error rendering table:** `{e}`")

    def _download_filename() -> str:
        set_language(lang())
        base_name = (
            "China_Climate_Target_Tracker_cn"
            if get_lang() == "CN"
            else "China_Climate_Target_Tracker_en"
        )
        if has_filters():
            return f"{base_name}_{i18n('筛选结果')}.xlsx"
        return f"{base_name}.xlsx"

    @render.download(filename=_download_filename)
    def download_data():
        set_language(lang())
        if has_filters():
            buffer = io.BytesIO()
            display_data(_apply_filters(df())).write_excel(buffer)
            buffer.seek(0)
            yield buffer.getvalue()
        else:
            yield fetch_raw_data(lang()).getvalue()

    @reactive.effect
    @reactive.event(input.mytable_page)
    async def _():
        current_page.set(input.mytable_page())


app = App(app_ui, server, debug=False)
