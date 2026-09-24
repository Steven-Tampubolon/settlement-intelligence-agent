"""
Test untuk backend/scheduler/trigger_resolver.py
Jalankan: pytest tests/test_trigger_resolver.py -v
"""
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from backend.database import init_db, get_db_path
from backend.scheduler.trigger_resolver import resolve_pending_triggers, _mark_resolved


def _insert_trigger(store_id: str, trigger_type: str, condition_data: dict) -> int:
    """Helper: insert pending trigger ke database, return id."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.execute(
        """
        INSERT INTO pending_triggers (store_id, trigger_type, condition_data, is_resolved)
        VALUES (?, ?, ?, ?)
        """,
        (store_id, trigger_type, json.dumps(condition_data), False),
    )
    trigger_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return trigger_id


def _get_trigger(trigger_id: int) -> dict | None:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM pending_triggers WHERE id = ?", (trigger_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


@pytest.fixture(autouse=True)
def setup_db():
    """Pastikan database dan tabel ada sebelum setiap test."""
    init_db()
    yield
    # Cleanup: hapus trigger test setelah setiap test
    conn = sqlite3.connect(get_db_path())
    conn.execute("DELETE FROM pending_triggers WHERE store_id = 'test_store'")
    conn.commit()
    conn.close()


class TestTriggerResolver:

    def test_trigger_resolved_when_date_passed(self):
        """
        Trigger dengan expected_date kemarin harus di-resolve
        dan follow-up alert terkirim.
        """
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        trigger_id = _insert_trigger(
            store_id="test_store",
            trigger_type="restock_after_settlement",
            condition_data={
                "expected_date": yesterday,
                "item": "mie instan",
                "cost": 6000000,
                "settlement_id": "SPJ-TEST",
            }
        )

        with patch("backend.scheduler.trigger_resolver.send_followup_alert") as mock_send:
            mock_send.return_value = {"sent": True}
            resolve_pending_triggers()

        # Verifikasi trigger sudah resolved
        trigger = _get_trigger(trigger_id)
        assert trigger["is_resolved"] == 1, "Trigger harus resolved setelah tanggal lewat"

        # Verifikasi follow-up alert dipanggil
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args.kwargs["store_id"] == "test_store"
        assert "mie instan" in call_args.kwargs["message"]

    def test_trigger_not_resolved_when_date_future(self):
        """
        Trigger dengan expected_date besok TIDAK boleh di-resolve.
        """
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        trigger_id = _insert_trigger(
            store_id="test_store",
            trigger_type="restock_after_settlement",
            condition_data={
                "expected_date": tomorrow,
                "item": "sabun mandi",
                "cost": 4500000,
                "settlement_id": "SPJ-FUTURE",
            }
        )

        with patch("backend.scheduler.trigger_resolver.send_followup_alert") as mock_send:
            resolve_pending_triggers()

        # Trigger belum waktunya — harus tetap pending
        trigger = _get_trigger(trigger_id)
        assert trigger["is_resolved"] == 0, "Trigger belum waktunya, harus tetap pending"
        mock_send.assert_not_called()

    def test_trigger_resolved_when_date_today(self):
        """Trigger dengan expected_date hari ini harus di-resolve."""
        today = date.today().isoformat()
        trigger_id = _insert_trigger(
            store_id="test_store",
            trigger_type="restock_after_settlement",
            condition_data={
                "expected_date": today,
                "item": "deterjen",
                "cost": 3800000,
                "settlement_id": "SPJ-TODAY",
            }
        )

        with patch("backend.scheduler.trigger_resolver.send_followup_alert") as mock_send:
            mock_send.return_value = {"sent": True}
            resolve_pending_triggers()

        trigger = _get_trigger(trigger_id)
        assert trigger["is_resolved"] == 1
        mock_send.assert_called_once()

    def test_followup_message_contains_item_and_cost(self):
        """Pesan follow-up harus menyebut item dan cost."""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _insert_trigger(
            store_id="test_store",
            trigger_type="restock_after_settlement",
            condition_data={
                "expected_date": yesterday,
                "item": "mie instan karton",
                "cost": 6000000,
                "settlement_id": "SPJ-MSG",
            }
        )

        captured_message = {}

        def capture_alert(store_id, message):
            captured_message["text"] = message
            return {"sent": True}

        with patch("backend.scheduler.trigger_resolver.send_followup_alert", side_effect=capture_alert):
            resolve_pending_triggers()

        assert "mie instan karton" in captured_message["text"]
        assert "6.000.000" in captured_message["text"]

    def test_already_resolved_trigger_not_processed(self):
        """Trigger yang sudah resolved tidak diproses ulang."""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        conn = sqlite3.connect(get_db_path())
        cursor = conn.execute(
            """
            INSERT INTO pending_triggers
                (store_id, trigger_type, condition_data, is_resolved)
            VALUES (?, ?, ?, ?)
            """,
            ("test_store", "restock_after_settlement",
             json.dumps({"expected_date": yesterday, "item": "x", "cost": 1000000}),
             True),  # sudah resolved
        )
        conn.commit()
        conn.close()

        with patch("backend.scheduler.trigger_resolver.send_followup_alert") as mock_send:
            resolve_pending_triggers()

        mock_send.assert_not_called()