import asyncio
import os
import sqlite3
from datetime import datetime

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from backend.config import TELEGRAM_BOT_TOKEN, DATABASE_URL, LLM_MODEL_NAME


def get_db_path() -> str:
    return DATABASE_URL.replace("sqlite:///", "")


def send_alert(store_id: str, validated_output: dict) -> dict:
    """
    Kirim alert ke Telegram untuk satu toko.
    validated_output adalah output dari OutputValidator Langflow.
    """
    # Ambil chat_id dari database
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT telegram_chat_id, owner_name FROM stores WHERE id = ?", (store_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise ValueError(f"Store '{store_id}' tidak ditemukan di database")

    chat_id = row["telegram_chat_id"]
    owner_name = row["owner_name"]

    # Ambil data dari validated_output
    is_valid = validated_output.get("valid", False)
    parsed = validated_output.get("parsed", {})

    if not is_valid or not parsed:
        # Gunakan fallback message
        message = _build_fallback_message(validated_output)
        button_text = "Lihat Detail"
        model_used = "fallback_template"
    else:
        message = parsed.get("full_message", "")
        button_text = parsed.get("action_button", "Lihat Detail")
        model_used = LLM_MODEL_NAME

    # Build inline keyboard
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ {button_text}", callback_data=f"confirm_{store_id}"),
        InlineKeyboardButton("🔄 Detail", callback_data=f"detail_{store_id}"),
    ]])

    # Kirim ke Telegram
    async def _send():
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    asyncio.run(_send())

    # Simpan ke history
    _save_alert_history(
        store_id=store_id,
        status=parsed.get("status_line", "unknown"),
        message_sent=message,
        llm_model_used=model_used,
        validation_passed=is_valid,
    )

    print(f"  ✅ Alert terkirim ke {owner_name} ({chat_id})")
    return {"sent": True, "timestamp": datetime.now().isoformat(), "store_id": store_id}


def _build_fallback_message(validated_output: dict) -> str:
    reason = validated_output.get("reason", "unknown")
    return (
        f"⚠️ Alert Settlement\n"
        f"Sistem mendeteksi kondisi yang perlu diperhatikan.\n"
        f"Silakan cek dashboard untuk detail lengkap.\n"
        f"<i>(Fallback — validasi gagal: {reason})</i>"
    )


def _save_alert_history(
    store_id: str,
    status: str,
    message_sent: str,
    llm_model_used: str,
    validation_passed: bool,
):
    conn = sqlite3.connect(get_db_path())
    conn.execute(
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