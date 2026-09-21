"""
Layer 3C — Telegram Sender
BOLEH: Kirim pesan + inline keyboard, simpan history ke DB
TIDAK BOLEH: Format ulang isi pesan, buat keputusan berdasarkan respons
"""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from langflow.custom import CustomComponent


class TelegramSender(CustomComponent):
    display_name = "Telegram Sender"
    description = "Kirim alert ke Telegram dengan inline keyboard aksi"

    def build_config(self):
        return {
            "validated_output": {
                "display_name": "Output Validator Result",
                "required": True,
            },
            "chat_id": {
                "display_name": "Telegram Chat ID",
                "required": True,
            },
            "store_id": {
                "display_name": "Store ID",
                "required": True,
            },
            "model_used": {
                "display_name": "LLM Model Used",
                "value": "groq/compound-mini",
                "required": False,
            },
        }

    def build(
        self,
        validated_output: dict,
        chat_id: str,
        store_id: str,
        model_used: str = "groq/compound-mini",
    ) -> dict:
        return send_telegram_alert(validated_output, chat_id, store_id, model_used)


# ── Fungsi standalone ─────────────────────────────────────────────────
def send_telegram_alert(
    validated_output: dict,
    chat_id: str,
    store_id: str,
    model_used: str = "groq/compound-mini",
) -> dict:
    """
    Kirim alert ke Telegram dan catat ke database.
    validated_output bisa dari LLM atau fallback template.
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN tidak ada di environment variables")

    parsed = validated_output.get("parsed") or validated_output
    message = parsed["full_message"]
    button_text = parsed.get("action_button", "Lihat Detail")
    is_fallback = parsed.get("_fallback_used", False)

    # Build inline keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"✅ {button_text}",
                callback_data=f"confirm_{store_id}"
            ),
            InlineKeyboardButton(
                "🔄 Detail",
                callback_data=f"detail_{store_id}"
            ),
        ]
    ])

    # Kirim ke Telegram
    import asyncio

    async def _send():
        bot = telegram.Bot(token=bot_token)
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    asyncio.run(_send())

    # Catat ke alert_history
    _save_alert_history(
        store_id=store_id,
        status=parsed.get("status_line", ""),
        message_sent=message,
        llm_model_used=model_used if not is_fallback else "fallback_template",
        validation_passed=validated_output.get("valid", True),
    )

    return {
        "sent": True,
        "timestamp": datetime.now().isoformat(),
        "store_id": store_id,
        "chat_id": chat_id,
        "fallback_used": is_fallback,
    }


def _save_alert_history(
    store_id: str,
    status: str,
    message_sent: str,
    llm_model_used: str,
    validation_passed: bool,
):
    """Simpan ke SQLite. Database path dari env var."""
    db_path = os.environ.get("DATABASE_URL", "sqlite:///./settlement_agent.db")
    db_path = db_path.replace("sqlite:///", "")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO alert_history
            (store_id, status, message_sent, llm_model_used, validation_passed, sent_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (store_id, status, message_sent, llm_model_used, validation_passed,
         datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()