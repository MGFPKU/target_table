from htmltools import tags, Tag
import polars as pl
import math
from i18n import i18n, LANG

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
            *render_dropdown(current, total),
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

def render_dropdown(current: int, total: int):
    dropdown = tags.select(
        *[tags.option(str(i), selected=(i == current)) for i in range(1, total + 1)],
        onchange=f'Shiny.setInputValue("{id}_page", parseInt(this.value), {{priority: "event"}})',
        # style="margin-left: 1em;",
    )
    if LANG == 'CN':
        text1 = tags.span(i18n("第"), style="margin-left: 4px;"),
        text2 = tags.span(i18n("页")),
        return (text1, dropdown, text2)
    elif LANG == 'EN':
        text = tags.span(i18n("页"), style="margin-left: 4px;"),
        return (text, dropdown)
    else:
        raise ValueError(f"Unsupported language: {LANG}")

def _col_class(col_name: str) -> str:
    """Convert column name to a valid CSS class name by replacing spaces with hyphens."""
    return f"col-{col_name.replace(' ', '-')}"

def output_paginated_table(
    id: str, df: pl.DataFrame, page: int = 1, per_page: int = 10
) -> Tag:
    # Extract page slice
    total_rows = df.shape[0]
    total_pages = max(math.ceil(total_rows / per_page), 1)
    start = (page - 1) * per_page
    end = start + per_page
    slice_df = df[start:end, :6]  # first 6 columns only

    # Header (display underscores as spaces)
    thead = tags.thead(
        tags.tr(*(tags.th(col.replace("_", " "), class_=_col_class(col)) for col in slice_df.columns))
    )

    # Rows
    tbody = tags.tbody()
    for row in slice_df.iter_rows():
        policy_id = str(row[1])  # Assume column index 1 is “政策动态”

        # Build each cell with a column-specific class
        row_cells = [
            tags.td(
                str(cell),
                class_=_col_class(col_name)
            )
            for col_name, cell in zip(slice_df.columns, row)
        ]

        # Wrap the row with onclick handler
        row_tag = tags.tr(
            *row_cells,
            onclick=f'Shiny.setInputValue("{id}", "{policy_id}", {{priority: "event"}});',
            class_="clickable-row"
        )
        tbody.append(row_tag)

    # Pagination controls
    pagination = render_pagination(id, page, total_pages)

    table = tags.table(thead, tbody, class_="custom-table")
    return tags.div(
        tags.style("""
            .custom-table-container {
                width: 100%;
                overflow-x: auto;
            }
            .custom-table {
                border-collapse: collapse;
                width: 100%;
                table-layout: fixed;
            }
            .custom-table th {
                text-align: left;
                font-weight: bold;
                padding: 16px 8px;
                border-bottom: 2px solid #ddd; /* Thick bottom border for header */
                // white-space: nowrap; // Allow header to wrap if needed
            }
            .custom-table td {
                border: 1px solid #eee;
                padding: 14px 8px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            /* Remove vertical borders */
            .custom-table th,
            .custom-table td {
                border-left: none;
                border-right: none;
            }

            /* Allow wrapping for Policy column (政策动态/Policy) */
            .custom-table .col-政策动态,
            .custom-table .col-Policy {
                white-space: normal;
                word-break: break-word;
            }

            /* Allow wrapping for Publisher column (发布主体/Publisher) */
            .custom-table .col-发布主体,
            .custom-table .col-Publisher {
                white-space: normal;
                word-break: break-word;
            }

            /* Column widths: Direction, Target Year and Baseline Year narrower, Category wider */
            .custom-table .col-Direction,
            .custom-table .col-Target_Year_or_Period {
                width: 90px;
                min-width: 90px;
            }

            .custom-table .col-Baseline_Year {
                width: 80px;
                min-width: 80px;
            }

            .clickable-row {
                cursor: pointer;
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
            "经济体": ["A", "B", "C"] * 5,
            "政策动态": ["Policy 1", "Policy 2", "Policy 3"] * 5,
            "政策类型": ["Type 1", "Type 2", "Type 3"] * 5,
            "发布主体": ["Agency A", "Agency B", "Agency C"] * 5,
            "时间": ["2021-01-01", "2021-02-01", "2021-03-01"] * 5,
        }
    )

    print(output_paginated_table("test_table", df, page=1))
