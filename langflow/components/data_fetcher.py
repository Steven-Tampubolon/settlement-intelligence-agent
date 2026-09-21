"""
Layer 3A — Data Fetcher
BOLEH: Ambil data dari mock/API, normalisasi ke format standar
TIDAK BOLEH: Kalkulasi, natural language, keputusan
"""
import json
import os
from pathlib import Path
from langflow.custom import CustomComponent
from langflow.field_typing import Text


class DataFetcher(CustomComponent):
    display_name = "Data Fetcher"
    description = "Mengambil data settlement dari mock data (swap ke real API nanti)"

    def build_config(self):
        return {
            "store_id": {
                "display_name": "Store ID",
                "info": "ID toko yang akan dimonitor",
                "required": True,
            },
            "scenario": {
                "display_name": "Scenario (Mock)",
                "info": "Pilih skenario: S1_AMAN, S2_WASPADA, S3_KRITIS, S4_RESTOCK_AMAN, S5_MULTI_SETTLEMENT",
                "required": False,
                "value": "S1_AMAN",
            },
        }

    def build(self, store_id: str, scenario: str = "S1_AMAN") -> dict:
        """
        Untuk MVP: load dari mock data file.
        Untuk production: ganti dengan HTTP call ke marketplace API.
        Interface output TIDAK BERUBAH.
        """
        mock_data_path = Path(__file__).parent.parent / "mock_data" / "store_scenarios.json"

        with open(mock_data_path, "r", encoding="utf-8") as f:
            all_scenarios = json.load(f)

        if scenario not in all_scenarios["scenarios"]:
            raise ValueError(
                f"Scenario '{scenario}' tidak ditemukan. "
                f"Pilih dari: {list(all_scenarios['scenarios'].keys())}"
            )

        data = all_scenarios["scenarios"][scenario]["data"]

        # Override store_id dari parameter jika berbeda dari mock
        data["store_id"] = store_id

        # Validasi field wajib
        required_fields = [
            "owner_name", "current_cash_balance",
            "average_daily_expense", "settlements"
        ]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Field wajib '{field}' tidak ada di data")

        return data


# ── Untuk test standalone (tanpa Langflow) ────────────────────────────
def fetch_store_data(store_id: str, scenario: str = "S1_AMAN") -> dict:
    """
    Fungsi standalone — bisa dipanggil dari unit test tanpa Langflow.
    Identik dengan logika build() di atas.
    """
    mock_data_path = (
        Path(__file__).parent.parent / "mock_data" / "store_scenarios.json"
    )
    with open(mock_data_path, "r", encoding="utf-8") as f:
        all_scenarios = json.load(f)

    if scenario not in all_scenarios["scenarios"]:
        raise ValueError(f"Scenario '{scenario}' tidak ditemukan.")

    data = all_scenarios["scenarios"][scenario]["data"].copy()
    data["store_id"] = store_id
    return data