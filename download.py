
from httpx._models import Response

from shiny import ui
import os
import httpx
import base64
import re

from i18n import i18n, LANG

GOOGLE_SCRIPT_URL: str | None = os.getenv("GOOGLE_SCRIPT_URL")

download_tab = ui.nav_panel(
                    "download_panel",
                    ui.HTML(f"{i18n("请填写您的机构名称和邮箱，以便我们通过邮件发送所选数据：")}<br><br>"),
                    ui.input_text("user_inst", i18n("机构名称:"), placeholder=i18n("请输入机构名称")),
                    ui.input_text("user_email", i18n("邮箱:"), placeholder=i18n("请输入邮箱")),
                    ui.output_text(id="nrow"),
                    ui.div(
                        ui.layout_columns(
                            ui.input_action_button(id="send_csv", label=i18n("发送 CSV")),
                            ui.input_action_button(id="send_excel", label=i18n("发送 Excel")),
                            ui.input_action_button("back1", i18n("返回列表"))
                        ),
                        class_="detail-buttons",
                    ),
                    ui.tags.script("""
                    document.addEventListener("DOMContentLoaded", function() {
                        const email = localStorage.getItem("user_email");
                        const inst = localStorage.getItem("user_inst");
                        if (email) {
                            const emailInput = document.getElementById("user_email");
                            if (emailInput) {
                                emailInput.value = email; // update UI
                                //Shiny.setInputValue("user_email", email); // update server input
                            }
                        }

                        if (inst) {
                            const instInput = document.getElementById("user_inst");
                            if (instInput) {
                                instInput.value = inst;
                                //Shiny.setInputValue("user_inst", inst);
                            }
                        }
                    });
                    Shiny.addCustomMessageHandler("storeUserInfo", function(message) {
                        localStorage.setItem("user_email", message.email);
                        localStorage.setItem("user_inst", message.inst);
                    });
                    """)
                )

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$")

async def send_to_email(input, session, fmt: str, data: bytes | str):
    email: str = input.user_email().strip()
    inst: str = input.user_inst().strip()

    # Validate email
    if not EMAIL_REGEX.match(email):
        ui.notification_show(i18n("📮 无效的邮箱地址，请检查输入。"), type="error")
        return

    # Validate institution (optional, but recommended)
    if len(inst) < 2:
        ui.notification_show(i18n("🏢 请输入机构名称（至少两个字符）。"), type="error")
        return

    # Save info in browser localStorage
    await session.send_custom_message("storeUserInfo", {
        "email": email,
        "inst": inst
    })
    
    if fmt == "xlsx":
        if not isinstance(data, bytes):
            raise ValueError("Excel format requires binary data")
        content_b64 = base64.b64encode(data).decode("utf-8")
    else:
        if not isinstance(data, str):
            raise ValueError("CSV format requires string data")
        content_b64 = base64.b64encode(data.encode("utf-8")).decode("utf-8")

    payload = {
        "email": email,
        "inst": inst,
        "format": fmt,
        "lang": LANG,
        "content": content_b64,
    }
    async with httpx.AsyncClient() as client:
        if not GOOGLE_SCRIPT_URL:
            raise ValueError("GOOGLE_SCRIPT_URL environment variable is not set.")
        response: Response =  await client.post(GOOGLE_SCRIPT_URL, json=payload)
        if response.status_code == 302:
            _ = ui.notification_show(i18n("📬 数据已发送至邮箱"), type="message")
        else:
            _ = ui.notification_show(i18n("❌ 数据发送失败: {}", response), type="error")