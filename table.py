from htmltools import tags, Tag
import polars as pl
import math
import json
import re
from collections.abc import Sequence
from i18n import i18n, get_lang
from data import CN_HEADER_MAP

DEFAULT_DISPLAY_COLUMNS = ("Metric", "Announced", "Target", "Target_Category")


def render_pagination(id: str, current: int, total: int) -> Tag:
    def page_btn(label, page, active=False):
        return tags.button(
            label,
            onclick=f'Shiny.setInputValue("{id}_page", {page}, {{priority: "event"}})',
            class_="page-btn" + (" active-page" if active else ""),
        )

    buttons = []

    # 首页 / 上一页
    buttons.append(page_btn(i18n("首页"), 1))
    buttons.append(page_btn(i18n("上一页"), max(1, current - 1)))

    # Page numbers
    # Page range: max 5 buttons, centered on current page
    start = max(1, current - 2)
    end = min(total, start + 4)
    # Adjust start again if we're near the end
    start = max(1, end - 4)

    for i in range(start, end + 1):
        buttons.append(page_btn(str(i), i, active=(i == current)))

    # 下一页 / 末页
    buttons.append(page_btn(i18n("下一页"), min(total, current + 1)))
    buttons.append(page_btn(i18n("末页"), total))

    return tags.div(
        tags.style("""
            .page-btn {
                border: 1px solid #ccc;
                background: white;
                padding: 4px 10px;
                margin: 0 2px;
                cursor: pointer;
            }
            .page-btn:hover {
                background-color: rgb(22, 171, 127);
                color: white;
            }
            .active-page {
                background-color: rgb(13, 97, 72);
                color: white;
                font-weight: bold;
            }
        """),
        tags.div(
            *buttons,
            *render_dropdown(id, current, total),
            style=(
                "display: flex; "
                "align-items: center; "
                "flex-wrap: wrap; "
                "gap: 4px; "
                "justify-content: center;"
                "margin: 1em; "
            ),
        ),
    )


def render_dropdown(id: str, current: int, total: int):
    dropdown = tags.select(
        *[tags.option(str(i), selected=(i == current)) for i in range(1, total + 1)],
        onchange=f'Shiny.setInputValue("{id}_page", parseInt(this.value), {{priority: "event"}})',
        # style="margin-left: 1em;",
    )
    if get_lang() == "CN":
        text1 = (tags.span(i18n("第"), style="margin-left: 4px;"),)
        text2 = (tags.span(i18n("页")),)
        return (text1, dropdown, text2)
    elif get_lang() == "EN":
        text = (tags.span(i18n("页"), style="margin-left: 4px;"),)
        return (text, dropdown)
    else:
        raise ValueError(f"Unsupported language: {get_lang()}")


def _col_class(col_name: str) -> str:
    """Convert column name to a valid CSS class name."""
    return f"col-{re.sub(r'[^A-Za-z0-9_-]+', '-', col_name).strip('-')}"


def _normalize_metric(value: object) -> str:
    if value is None:
        return ""
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", str(value))
    return re.sub(r"\s+", " ", text).strip()


def _display_value(value: object) -> str:
    if value is None:
        return "N/A"
    return str(value)


def _metric_rowspans(rows: list[dict[str, object]]) -> dict[int, int]:
    spans: dict[int, int] = {}
    index = 0
    while index < len(rows):
        metric = _normalize_metric(rows[index].get("Metric"))
        next_index = index + 1
        while (
            next_index < len(rows)
            and _normalize_metric(rows[next_index].get("Metric")) == metric
        ):
            next_index += 1
        spans[index] = next_index - index
        index = next_index
    return spans


def output_paginated_table(
    id: str,
    df: pl.DataFrame,
    page: int = 1,
    per_page: int = 10,
    display_columns: Sequence[str] = DEFAULT_DISPLAY_COLUMNS,
) -> Tag:
    # Extract page slice
    missing_cols = [col for col in display_columns if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing display columns: {', '.join(missing_cols)}")

    total_rows = df.shape[0]
    total_pages = max(math.ceil(total_rows / per_page), 1)
    start = (page - 1) * per_page
    end = start + per_page
    slice_df = df.select(list(display_columns)).slice(start, per_page)
    rows = slice_df.to_dicts()
    metric_spans = _metric_rowspans(rows)

    # Header — use Chinese labels in CN mode, underscore→space in EN mode
    thead = tags.thead(
        tags.tr(
            *(
                tags.th(
                    CN_HEADER_MAP.get(col, col.replace("_", " "))
                    if get_lang() == "CN"
                    else col.replace("_", " "),
                    class_=_col_class(col),
                )
                for col in slice_df.columns
            )
        )
    )

    # Rows
    tbody = tags.tbody()
    for row_index, row in enumerate(rows):
        policy_id = _display_value(row.get("Document", row.get("Target", "")))

        # Build each cell with a column-specific class
        row_cells = []
        for col_name in slice_df.columns:
            if col_name == "Metric":
                rowspan = metric_spans.get(row_index)
                if rowspan is None:
                    continue
                cell_attrs = {"class_": _col_class(col_name)}
                if rowspan > 1:
                    cell_attrs["rowspan"] = str(rowspan)
                row_cells.append(tags.td(_display_value(row[col_name]), **cell_attrs))
            else:
                row_cells.append(
                    tags.td(_display_value(row[col_name]), class_=_col_class(col_name))
                )

        # Wrap the row with onclick handler
        row_tag = tags.tr(
            *row_cells,
            onclick=f'Shiny.setInputValue("{id}", {json.dumps(policy_id)}, {{priority: "event"}});',
            class_="clickable-row",
        )
        tbody.append(row_tag)

    # Pagination controls
    pagination = render_pagination(id, page, total_pages)

    table = tags.table(thead, tbody, class_="custom-table")
    return tags.div(
        tags.style("""
            .custom-table-container {
                width: 100%;
                max-width: 100%;
                overflow-x: auto;
            }
            .custom-table {
                border-collapse: collapse;
                width: 100%;
                max-width: 100%;
                table-layout: fixed;
            }
            .custom-table th {
                text-align: left;
                font-weight: bold;
                padding: 16px 8px;
                border-bottom: 2px solid #ddd; /* Thick bottom border for header */
                white-space: normal;
                overflow-wrap: anywhere;
            }
            .custom-table td {
                border: 1px solid #eee;
                padding: 14px 8px;
                white-space: normal;
                overflow: hidden;
                text-overflow: ellipsis;
                overflow-wrap: anywhere;
            }

            /* Remove vertical borders */
            .custom-table th,
            .custom-table td {
                border-left: none;
                border-right: none;
            }

            .custom-table .col-Metric {
                width: 30%;
                word-break: break-word;
                vertical-align: top;
            }
            .custom-table .col-Announced {
                width: 12%;
            }
            .custom-table .col-Target {
                width: 42%;
            }
            .custom-table .col-Target_Category {
                width: 16%;
            }

            .clickable-row {
                transition: background-color 0.2s;
            }

            .clickable-row td {
                /* Ensures no text underlines or color overrides interfere */
                color: black;
                text-decoration: none;
            }
        """),
        tags.div(table, class_="custom-table-container"),
        pagination,
    )


if __name__ == "__main__":
    # Example usage
    df = pl.DataFrame(
        {
            "Metric": ["A", "A", "B"] * 5,
            "Announced": ["2020", "2021", "2022"] * 5,
            "Target": ["by 2020, reach 10 percent", "by 2030, reach 20 percent", "during the 12th FYP (2011-2015), reduce by 15 percent"] * 5,
            "Target_Category": ["Energy", "Energy", "Industry"] * 5,
        }
    )

    print(output_paginated_table("test_table", df, page=1))
