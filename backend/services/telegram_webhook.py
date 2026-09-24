import os
import json
import sqlite3
from datetime import datetime

import telegram
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from backend.config import TELEGRAM_BOT_TOKEN, DATABASE_URL


def get_db_path() -> str:
    return DATABASE_URL.replace("sqlite:///", "")


def save_user_action(store_id: str, action: str):
    """Simpan aksi user ke alert_history."""
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        """
        UPDATE alert_history
        SET user_action = ?
        WHERE store_id = ? AND user_action IS NULL
        ORDER BY sent_at DESC
        LIMIT 1
        """,
        (action, store_id),
    )
    conn.commit()
    conn.close()


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle tombol inline keyboard dari alert Telegram.
    callback_data format: "confirm_{store_id}" atau "detail_{store_id}"
    """
    query = update.callback_query
    await query.answer()  # Hapus loading indicator di tombol

    data = query.data
    parts = data.split("_", 1)
    action = parts[0]       # "confirm" atau "detail"
    store_id = parts[1]     # "toko_andi_001"

    if action == "confirm":
        await _handle_confirm(query, store_id)
    elif action == "detail":
        await _handle_detail(query, store_id)


async def _handle_confirm(query, store_id: str):
    """User klik ✅ — tandai sudah dibaca dan buat trigger follow-up jika perlu."""
    save_user_action(store_id, "confirmed")

    # Buat pending_trigger jika keputusan terakhir adalah restock
    last_decision = _get_last_decision_data(store_id)
    if last_decision:
        decision = last_decision.get("pending_decision")
        if decision and decision.get("type") == "restock":
            best_settlement = decision.get("best_settlement")
            if best_settlement:
                _create_pending_trigger(
                    store_id=store_id,
                    trigger_type="restock_after_settlement",
                    condition_data={
                        "settlement_id": best_settlement.get("settlement_id", ""),
                        "expected_date": best_settlement.get("disbursement_date", ""),
                        "item": decision.get("item", ""),
                        "cost": decision.get("cost", 0),
                    }
                )
                print(f"  📌 Pending trigger dibuat untuk {store_id}: restock_after_settlement")

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(
        "✅ Noted! Alert sudah dikonfirmasi.\n"
        "Saya akan pantau dan kabari begitu settlement cair."
    )


def _get_last_decision_data(store_id: str) -> dict | None:
    """Ambil decision_data dari alert terakhir di database."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT decision_data FROM alert_history
        WHERE store_id = ? AND decision_data IS NOT NULL
        ORDER BY sent_at DESC LIMIT 1
        """,
        (store_id,),
    ).fetchone()
    conn.close()

    if not row or not row["decision_data"]:
        return None
    try:
        return json.loads(row["decision_data"])
    except (json.JSONDecodeError, TypeError):
        return None


def _create_pending_trigger(store_id: str, trigger_type: str, condition_data: dict):
    """Insert entry baru ke tabel pending_triggers."""
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        """
        INSERT INTO pending_triggers (store_id, trigger_type, condition_data, is_resolved)
        VALUES (?, ?, ?, ?)
        """,
        (store_id, trigger_type, json.dumps(condition_data), False),
    )
    conn.commit()
    conn.close()


async def _handle_detail(query, store_id: str):
    """User klik 🔄 Detail — tampilkan ringkasan dari history."""
    save_user_action(store_id, "detail_requested")

    # Ambil alert terakhir dari database
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT status, sent_at, llm_model_used, validation_passed
        FROM alert_history
        WHERE store_id = ?
        ORDER BY sent_at DESC
        LIMIT 1
        """,
        (store_id,),
    ).fetchone()
    conn.close()

    if not row:
        await query.message.reply_text("ℹ️ Tidak ada data history tersedia.")
        return

    sent_at = row["sent_at"][:19].replace("T", " ")
    validation = "✅ Valid" if row["validation_passed"] else "⚠️ Fallback"
    model = row["llm_model_used"]

    detail_text = (
        f"📊 *Detail Alert Terakhir*\n\n"
        f"🏪 Toko: `{store_id}`\n"
        f"🕐 Waktu: {sent_at} WIB\n"
        f"🤖 Model: {model}\n"
        f"✔️ Validasi: {validation}\n\n"
        f"Untuk monitoring manual, hubungi admin."
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Tutup", callback_data=f"close_{store_id}")
    ]])

    await query.message.reply_text(
        detail_text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def handle_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle tombol Tutup di detail view."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "👋 Halo! Saya Settlement Intelligence Agent.\n\n"
        "Saya akan mengirim alert otomatis setiap pagi pukul 06:00 WIB "
        "berisi ringkasan settlement dan kondisi kas toko Anda.\n\n"
        "Tidak perlu melakukan apa-apa — alert akan datang otomatis."
    )


def build_telegram_app() -> Application:
    """Build Telegram Application dengan semua handler."""
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CallbackQueryHandler(handle_close, pattern="^close_"))
    app.add_handler(CallbackQueryHandler(handle_callback))

    return app