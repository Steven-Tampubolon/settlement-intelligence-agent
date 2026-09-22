"""
Script sekali pakai — test kirim pesan ke Telegram.
Jalankan: python scripts/test_telegram.py
"""
import asyncio
import os
import sys
from pathlib import Path

# Supaya bisa import dari root project
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def test_send():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN tidak ada di .env")
        return

    # Ambil chat_id dari database
    import sqlite3
    db_path = os.environ.get("DATABASE_URL", "sqlite:///./settlement_agent.db").replace("sqlite:///", "")

    if not Path(db_path).exists():
        print("❌ Database belum ada. Jalankan dulu:")
        print("   python -c \"from backend.database import init_db, seed_demo_store; init_db(); seed_demo_store()\"")
        return

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT telegram_chat_id, owner_name FROM stores LIMIT 1").fetchone()
    conn.close()

    if not row:
        print("❌ Tidak ada toko di database.")
        return

    chat_id, owner_name = row
    print(f"✅ Kirim ke {owner_name} (chat_id: {chat_id})")

    bot = telegram.Bot(token=token)

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Oke, mengerti", callback_data="confirm_test"),
        InlineKeyboardButton("🔄 Detail", callback_data="detail_test"),
    ]])

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "✅ AMAN – Kas Rp 4.200.000, runway 14 hari\n"
            "💰 Dana masuk: Rp 11.010.000 (Shopee, 24 Sep)\n"
            "📌 Tidak ada aksi mendesak — pantau terus\n"
            "\n"
            "<i>— Settlement Intelligence Agent (test)</i>"
        ),
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    print("✅ Pesan terkirim! Cek Telegram Anda.")


asyncio.run(test_send())