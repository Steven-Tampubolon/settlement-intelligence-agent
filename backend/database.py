# backend/database.py
import sqlite3
import os
from backend.config import DATABASE_URL


def get_db_path() -> str:
    return DATABASE_URL.replace("sqlite:///", "")


def init_db():
    """Buat tabel jika belum ada."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS stores (
            id TEXT PRIMARY KEY,
            owner_name TEXT NOT NULL,
            telegram_chat_id TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS alert_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id TEXT REFERENCES stores(id),
            status TEXT NOT NULL,
            message_sent TEXT NOT NULL,
            llm_model_used TEXT NOT NULL,
            validation_passed BOOLEAN NOT NULL,
            user_action TEXT,
            decision_data TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS pending_triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id TEXT REFERENCES stores(id),
            trigger_type TEXT NOT NULL,
            condition_data TEXT NOT NULL,
            is_resolved BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()

    # Migrasi: tambahkan kolom decision_data jika database lama belum punya
    try:
        conn.execute("ALTER TABLE alert_history ADD COLUMN decision_data TEXT")
        conn.commit()
        print("✅ Migrasi: kolom decision_data ditambahkan ke alert_history")
    except sqlite3.OperationalError:
        pass  # Kolom sudah ada

    conn.close()


def get_all_active_stores() -> list[dict]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stores WHERE is_active = TRUE")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def seed_demo_store():
    """Tambahkan toko demo jika belum ada (untuk development)."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR IGNORE INTO stores (id, owner_name, telegram_chat_id, is_active)
        VALUES (?, ?, ?, ?)
        """,
        ("toko_andi_001", "Pak Andi", "7749965364", True),
    )
    conn.commit()
    conn.close()