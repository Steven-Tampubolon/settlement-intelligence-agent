# backend/scheduler/daily_monitor.py
import json
from datetime import datetime

from backend.config import LANGFLOW_FLOW_ID
from backend.database import get_all_active_stores
from backend.services.langflow_client import LangflowClient
from backend.services.alert_service import send_alert

client = LangflowClient()


def run_daily_monitoring(scenario_override: str | None = None):
    """
    Jalankan monitoring untuk semua toko aktif.
    scenario_override: paksa skenario tertentu (untuk demo/test).
    """
    if not LANGFLOW_FLOW_ID:
        print("⚠️  LANGFLOW_FLOW_ID belum diset di .env")
        return

    if not client.health_check():
        print(f"❌ Langflow tidak merespons di {client.base_url}")
        return

    stores = get_all_active_stores()
    if not stores:
        print("ℹ️  Tidak ada toko aktif di database.")
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Memulai monitoring {len(stores)} toko...")

    results = []
    for store in stores:
        scenario = scenario_override or "S1_AMAN"
        store_id = store["id"]
        print(f"  → {store_id} ({store['owner_name']}) — skenario: {scenario}")

        try:
            # Step 1: Jalankan flow di Langflow
            validated_output = client.run_flow(
                store_id=store_id,
                scenario=scenario,
            )
            print(f"    Flow selesai — valid: {validated_output.get('valid')}")

            # Step 2: Kirim alert ke Telegram
            result = send_alert(store_id=store_id, validated_output=validated_output)
            results.append({"store_id": store_id, "status": "ok", **result})

        except Exception as e:
            print(f"  ❌ Error pada {store_id}: {e}")
            results.append({"store_id": store_id, "status": "error", "error": str(e)})

    print(f"[{timestamp}] Selesai. {len([r for r in results if r['status'] == 'ok'])}/{len(stores)} berhasil.")
    return results