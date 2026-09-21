# backend/scheduler/daily_monitor.py
import os
from datetime import datetime
from backend.services.langflow_client import LangflowClient
from backend.database import get_all_active_stores

# Flow ID diisi setelah import flow ke Langflow UI
FLOW_ID = os.environ.get("LANGFLOW_FLOW_ID", "")

client = LangflowClient()


def run_daily_monitoring(scenario_override: str | None = None):
    """
    Jalankan monitoring untuk semua toko aktif.
    scenario_override: jika diisi, pakai skenario ini untuk semua toko (untuk demo/test).
    """
    if not FLOW_ID:
        print("⚠️  LANGFLOW_FLOW_ID belum diset. Monitoring tidak jalan.")
        return

    if not client.health_check():
        print(f"❌ Langflow tidak merespons di {client.base_url}")
        return

    stores = get_all_active_stores()
    if not stores:
        print("ℹ️  Tidak ada toko aktif di database.")
        return

    print(f"[{datetime.now().isoformat()}] Memulai monitoring {len(stores)} toko...")

    for store in stores:
        scenario = scenario_override or "S1_AMAN"
        print(f"  → {store['id']} ({store['owner_name']}) — skenario: {scenario}")
        try:
            result = client.run_flow(
                flow_id=FLOW_ID,
                store_id=store["id"],
                scenario=scenario,
            )
            print(f"  ✅ Selesai: {store['id']}")
        except Exception as e:
            print(f"  ❌ Error pada {store['id']}: {e}")