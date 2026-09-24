# backend/scheduler/trigger_resolver.py
import json
import sqlite3
from datetime import datetime

from backend.database import get_db_path
from backend.services.alert_service import send_followup_alert


def resolve_pending_triggers():
    """
    Dipanggil setiap kali daily_monitor jalan.
    Cek semua pending_triggers yang belum resolved,
    bandingkan dengan tanggal hari ini, kirim follow-up jika kondisi terpenuhi.
    """
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM pending_triggers WHERE is_resolved = FALSE"
    ).fetchall()
    conn.close()

    if not rows:
        return

    today = datetime.now().date().isoformat()
    print(f"  🔍 Cek {len(rows)} pending trigger...")

    for row in rows:
        try:
            condition = json.loads(row["condition_data"])
            trigger_type = row["trigger_type"]
            store_id = row["store_id"]

            if trigger_type == "restock_after_settlement":
                expected_date = condition.get("expected_date", "")
                if expected_date and expected_date <= today:
                    item = condition.get("item", "stok")
                    cost = condition.get("cost", 0)
                    cost_fmt = f"Rp {cost:,}".replace(",", ".")
                    message = (
                        f"💰 Settlement sudah waktunya cair.\n"
                        f"Aman untuk restock {item} ({cost_fmt}).\n"
                        f"Segera lakukan restock sesuai rencana."
                    )
                    send_followup_alert(store_id=store_id, message=message)
                    _mark_resolved(row["id"])
                    print(f"  ✅ Trigger resolved: {trigger_type} untuk {store_id}")

        except Exception as e:
            print(f"  ❌ Error resolve trigger {row['id']}: {e}")


def _mark_resolved(trigger_id: int):
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        "UPDATE pending_triggers SET is_resolved = TRUE WHERE id = ?",
        (trigger_id,)
    )
    conn.commit()
    conn.close()