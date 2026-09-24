import asyncio
import json
import os
import sqlite3
from datetime import datetime

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from backend.config import TELEGRAM_BOT_TOKEN, DATABASE_URL, LLM_MODEL_NAME
from langflow.logic.output_validator import generate_fallback_message


def get_db_path() -> str:
    return DATABASE_URL.replace("sqlite:///", "")


def send_alert(store_id: str, validated_output: dict) -> dict:
    """
    Kirim alert ke Telegram untuk satu toko.
    validated_output adalah output dari LangflowClient.run_flow() —
    selalu mengandung 'decision_data' setelah FIX #1.
    """
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

    is_valid = validated_output.get("valid", False)
    parsed = validated_output.get("parsed", {})
    decision_data = validated_output.get("decision_data", {})

    if not is_valid or not parsed:
        if decision_data:
            # Gunakan generate_fallback_message yang benar — mengandung angka asli
            fallback = generate_fallback_message(decision_data)
            message = fallback["full_message"]
            button_text = fallback["action_button"]
        else:
            # Kondisi darurat — decision_data juga tidak tersedia
            message = (
                "⚠️ Sistem mengalami gangguan saat memproses data toko Anda.\n"
                "Tim kami akan mengecek secara manual. Mohon maaf atas ketidaknyamanannya."
            )
            button_text = "Mengerti"
        model_used = "fallback_template"
    else:
        message = parsed.get("full_message", "")
        button_text = parsed.get("action_button", "Lihat Detail")
        model_used = LLM_MODEL_NAME

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"✅ {button_text}", callback_data=f"confirm_{store_id}"),
        InlineKeyboardButton("🔄 Detail", callback_data=f"detail_{store_id}"),
    ]])

    async def _send():
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    asyncio.run(_send())

    _save_alert_history(
        store_id=store_id,
        status=parsed.get("status_line", "unknown") if parsed else "fallback",
        message_sent=message,
        llm_model_used=model_used,
        validation_passed=is_valid,
        decision_data=decision_data,
    )

    print(f"  ✅ Alert terkirim ke {owner_name} ({chat_id})")
    return {"sent": True, "timestamp": datetime.now().isoformat(), "store_id": store_id}


def send_followup_alert(store_id: str, message: str) -> dict:
    """Kirim follow-up alert tanpa inline keyboard — untuk trigger resolver."""
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

    async def _send():
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=chat_id, text=message)

    asyncio.run(_send())
    print(f"  ✅ Follow-up terkirim ke {owner_name} ({chat_id})")
    return {"sent": True, "timestamp": datetime.now().isoformat(), "store_id": store_id}


def _save_alert_history(
    store_id: str,
    status: str,
    message_sent: str,
    llm_model_used: str,
    validation_passed: bool,
    decision_data: dict = None,
):
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        """
        INSERT INTO alert_history
            (store_id, status, message_sent, llm_model_used,
             validation_passed, decision_data, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            store_id, status, message_sent, llm_model_used,
            validation_passed,
            json.dumps(decision_data, ensure_ascii=False) if decision_data else None,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()