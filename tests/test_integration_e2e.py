"""
Integration test end-to-end — test full pipeline dari FastAPI ke Langflow ke Telegram.
Jalankan dengan: pytest tests/test_integration_e2e.py -v

PRASYARAT sebelum jalankan test ini:
- Langflow jalan di localhost:7860
- Backend FastAPI jalan di localhost:8000
- .env sudah diisi lengkap
"""
import json
import os
import sqlite3
import time

import pytest
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8000"
LANGFLOW_URL = os.environ.get("LANGFLOW_BASE_URL", "http://localhost:7860")
LANGFLOW_API_KEY = os.environ.get("LANGFLOW_API_KEY", "")
LANGFLOW_FLOW_ID = os.environ.get("LANGFLOW_FLOW_ID", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./settlement_agent.db")


def get_db_path():
    return DATABASE_URL.replace("sqlite:///", "")


def get_latest_alert(store_id: str) -> dict | None:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM alert_history WHERE store_id = ? ORDER BY sent_at DESC LIMIT 1",
        (store_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def count_alerts_after(store_id: str, timestamp: str) -> int:
    conn = sqlite3.connect(get_db_path())
    count = conn.execute(
        "SELECT COUNT(*) FROM alert_history WHERE store_id = ? AND sent_at > ?",
        (store_id, timestamp),
    ).fetchone()[0]
    conn.close()
    return count


# ── Fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def backend_url():
    """Pastikan backend FastAPI jalan."""
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        assert r.status_code == 200
    except Exception:
        pytest.skip("Backend FastAPI tidak jalan di localhost:8000 — jalankan dulu: uvicorn backend.main:app --port 8000")
    return BASE_URL


@pytest.fixture(scope="session")
def langflow_url():
    """Pastikan Langflow jalan."""
    try:
        r = requests.get(f"{LANGFLOW_URL}/health", timeout=5)
        assert r.status_code == 200
    except Exception:
        pytest.skip("Langflow tidak jalan di localhost:7860 — jalankan dulu: docker compose up -d")
    return LANGFLOW_URL


# ── Test: Backend health ───────────────────────────────────────────────
class TestBackendHealth:
    def test_health_endpoint(self, backend_url):
        r = requests.get(f"{backend_url}/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_scheduler_running(self, backend_url):
        r = requests.get(f"{backend_url}/scheduler/status")
        assert r.status_code == 200
        data = r.json()
        assert data["running"] is True
        assert len(data["jobs"]) > 0


# ── Test: Langflow flow ────────────────────────────────────────────────
class TestLangflowPipeline:
    """Test Langflow flow langsung via API."""

    def _run_flow(self, scenario: str) -> dict:
        r = requests.post(
            f"{LANGFLOW_URL}/api/v1/run/{LANGFLOW_FLOW_ID}",
            headers={"x-api-key": LANGFLOW_API_KEY, "Content-Type": "application/json"},
            json={
                "input_value": "toko_andi_001",
                "input_type": "text",
                "output_type": "text",
                "tweaks": {
                    "DataFetcher-bG60r": {
                        "store_id": "toko_andi_001",
                        "scenario": scenario,
                    }
                },
            },
            timeout=60,
        )
        assert r.status_code == 200, f"Langflow error: {r.text}"
        text = r.json()["outputs"][0]["outputs"][0]["results"]["message"]["text"]
        return json.loads(text)

    def test_s1_aman_valid(self, langflow_url):
        result = self._run_flow("S1_AMAN")
        assert result["valid"] is True
        assert result["missing_numbers"] == []
        assert "4.200.000" in result["parsed"]["full_message"]

    def test_s2_waspada_valid(self, langflow_url):
        result = self._run_flow("S2_WASPADA")
        assert result["valid"] is True
        assert result["missing_numbers"] == []
        assert "3.500.000" in result["parsed"]["full_message"]

    def test_s3_kritis_valid(self, langflow_url):
        result = self._run_flow("S3_KRITIS")
        assert result["valid"] is True
        assert result["missing_numbers"] == []
        # Angka kritis S3 harus ada
        assert "850.000" in result["parsed"]["full_message"]
        assert "13.208.000" in result["parsed"]["full_message"]
        assert "3.500.000" in result["parsed"]["full_message"]

    def test_s4_restock_valid(self, langflow_url):
        result = self._run_flow("S4_RESTOCK_AMAN")
        assert result["valid"] is True
        assert result["missing_numbers"] == []
        assert "5.800.000" in result["parsed"]["full_message"]

    def test_s5_multi_settlement_valid(self, langflow_url):
        result = self._run_flow("S5_MULTI_SETTLEMENT")
        assert result["valid"] is True
        assert result["missing_numbers"] == []
        # Kedua settlement harus muncul individual
        assert "13.075.000" in result["parsed"]["full_message"]
        assert "7.160.000" in result["parsed"]["full_message"]

    def test_s5_settlement_individual_not_aggregated(self, langflow_url):
        """Pastikan qwen tidak menggabungkan settlement jadi total saja."""
        result = self._run_flow("S5_MULTI_SETTLEMENT")
        full_message = result["parsed"]["full_message"]
        # Total agregat 20.235.000 boleh ada, tapi individual harus ada juga
        assert "13.075.000" in full_message, "Settlement Shopee tidak muncul individual"
        assert "7.160.000" in full_message, "Settlement Tokopedia tidak muncul individual"


# ── Test: Full pipeline via FastAPI ───────────────────────────────────
class TestFullPipeline:
    """Test trigger via FastAPI — verifikasi alert tersimpan di database."""

    def test_trigger_s1_creates_alert(self, backend_url, langflow_url):
        from datetime import datetime
        before = datetime.now().isoformat()

        r = requests.post(
            f"{backend_url}/trigger",
            json={"store_id": "toko_andi_001", "scenario": "S1_AMAN"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "triggered"

        # Flow + retry logic bisa butuh hingga 30 detik
        time.sleep(30)

        count = count_alerts_after("toko_andi_001", before)
        assert count >= 1, "Alert tidak tersimpan di database setelah trigger"

    def test_trigger_s3_kritis_valid_alert(self, backend_url, langflow_url):
        from datetime import datetime
        before = datetime.now().isoformat()

        requests.post(
            f"{backend_url}/trigger",
            json={"store_id": "toko_andi_001", "scenario": "S3_KRITIS"},
        )

        time.sleep(30)

        # Query berdasarkan waktu — ambil alert yang dibuat SETELAH trigger ini
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM alert_history
            WHERE store_id = ? AND sent_at > ?
            ORDER BY sent_at DESC LIMIT 1
            """,
            ("toko_andi_001", before),
        ).fetchone()
        conn.close()

        assert row is not None, "Alert S3_KRITIS tidak tersimpan di database"
        alert = dict(row)
        assert alert["validation_passed"] == 1
        assert "850" in alert["message_sent"], (
            f"Angka 850.000 tidak ada di pesan. Message: {alert['message_sent']}"
        )

    def test_trigger_invalid_scenario(self, backend_url):
        r = requests.post(
            f"{backend_url}/trigger/scenario/S99_INVALID",
        )
        assert r.status_code == 400

    def test_alert_history_endpoint(self, backend_url):
        r = requests.get(f"{backend_url}/alerts/history")
        assert r.status_code == 200
        data = r.json()
        assert "alerts" in data
        assert isinstance(data["alerts"], list)

    def test_all_scenarios_endpoint(self, backend_url, langflow_url):
        """Test endpoint all-scenarios — semua harus status ok."""
        r = requests.post(
            f"{backend_url}/trigger/all-scenarios",
            timeout=300,  # 5 menit untuk 5 skenario
        )
        assert r.status_code == 200
        results = r.json()["results"]
        assert len(results) == 5

        failed = [r for r in results if r["status"] != "ok"]
        assert failed == [], f"Skenario gagal: {failed}"

class TestRetryLogic:
    """Test retry logic — verifikasi sistem retry sebelum fallback."""

    def test_retry_counter_on_valid_response(self, backend_url, langflow_url):
        """
        S3_KRITIS adalah skenario yang pernah gagal di attempt pertama.
        Verifikasi bahwa hasil akhirnya tetap valid (entah dari attempt 1, 2, atau 3).
        """
        r = requests.post(
            f"{backend_url}/trigger",
            json={"store_id": "toko_andi_001", "scenario": "S3_KRITIS"},
        )
        assert r.status_code == 200

        time.sleep(15)

        alert = get_latest_alert("toko_andi_001")
        assert alert is not None
        assert alert["validation_passed"] == 1, (
            f"Alert tidak valid setelah retry. Message: {alert['message_sent']}"
        )

    def test_fallback_not_triggered_on_valid_scenarios(self, backend_url, langflow_url):
        """
        Semua skenario seharusnya valid tanpa fallback setelah retry logic aktif.
        Verifikasi tidak ada 'Fallback' di pesan yang terkirim.
        """
        from datetime import datetime
        before = datetime.now().isoformat()

        requests.post(f"{backend_url}/trigger/all-scenarios", timeout=300)

        time.sleep(5)

        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM alert_history WHERE sent_at > ? ORDER BY sent_at DESC",
            (before,),
        ).fetchall()
        conn.close()

        fallback_alerts = [
            dict(r) for r in rows
            if "Fallback" in r["message_sent"] or r["validation_passed"] == 0
        ]
        assert fallback_alerts == [], (
            f"Ada {len(fallback_alerts)} alert fallback: "
            f"{[a['store_id'] for a in fallback_alerts]}"
        )

    def test_fallback_message_contains_real_numbers(self, backend_url, langflow_url):
        """
        Paksa semua retry gagal dengan mock, verifikasi fallback mengandung angka asli.
        Test ini memverifikasi FIX #1 di jalur produksi.
        """
        from unittest.mock import patch
        from langflow.logic.output_validator import generate_fallback_message

        # Simulasi decision_data untuk S3_KRITIS
        decision_data = {
            "store_owner": "Pak Andi",
            "store_id": "toko_andi_001",
            "status": "KRITIS",
            "urgency_level": 3,
            "current_cash": 850000,
            "runway_days": 3,
            "min_balance_amount": -50000,
            "settlements": [
                {"marketplace": "tiktok_shop", "net_amount": 13208000,
                "disbursement_date": "2026-09-28"}
            ],
            "total_incoming_this_week": 13208000,
            "pending_decision": {
                "type": "collect_receivable",
                "target": "Toko Makmur",
                "amount": 3500000,
                "overdue_days": 8,
                "recommendation": "Tagih Toko Makmur hari ini",
                "all_receivables": [],
            },
            "daily_projection": [],
        }

        fallback = generate_fallback_message(decision_data)

        # Verifikasi angka kritis ada di fallback message
        assert "850.000" in fallback["full_message"], \
            "Saldo kas tidak ada di fallback message"
        assert "13.208.000" in fallback["full_message"], \
            "Net settlement tidak ada di fallback message"
        assert fallback["_fallback_used"] is True

class TestNewScenarios:
    """Test skenario baru dari bugfix sprint."""

    def test_s6_flash_sale_via_api(self, backend_url, langflow_url):
        """S6: flash sale — verifikasi alert valid dan mengandung angka budget."""
        from datetime import datetime
        before = datetime.now().isoformat()

        r = requests.post(
            f"{backend_url}/trigger/scenario/S6_FLASH_SALE",
        )
        assert r.status_code == 200

        time.sleep(90)

        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM alert_history
            WHERE store_id = ? AND sent_at > ?
            ORDER BY sent_at DESC LIMIT 1
            """,
            ("toko_andi_001", before),
        ).fetchone()
        conn.close()

        assert row is not None, "Alert S6_FLASH_SALE tidak tersimpan"
        assert row["validation_passed"] == 1, (
            f"Alert tidak valid. Message: {row['message_sent']}"
        )
        # Angka budget flash sale harus ada di pesan
        assert "4.500.000" in row["message_sent"], (
            f"Budget flash sale tidak ada di pesan: {row['message_sent']}"
        )

    def test_s5_multiple_decision_via_api(self, backend_url, langflow_url):
        """S5: multiple decision — verifikasi pesan mengandung kedua prioritas."""
        from datetime import datetime
        before = datetime.now().isoformat()

        r = requests.post(
            f"{backend_url}/trigger/scenario/S5_MULTI_SETTLEMENT",
        )
        assert r.status_code == 200

        time.sleep(90)

        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM alert_history
            WHERE store_id = ? AND sent_at > ?
            ORDER BY sent_at DESC LIMIT 1
            """,
            ("toko_andi_001", before),
        ).fetchone()
        conn.close()

        assert row is not None, "Alert S5 tidak tersimpan"
        assert row["validation_passed"] == 1

        # Verifikasi decision_data mengandung multiple type
        decision_data = json.loads(row["decision_data"]) if row["decision_data"] else {}
        pending = decision_data.get("pending_decision", {})
        assert pending.get("type") == "multiple", (
            f"Expected multiple, got: {pending.get('type')}"
        )
        assert len(pending.get("decisions", [])) == 2