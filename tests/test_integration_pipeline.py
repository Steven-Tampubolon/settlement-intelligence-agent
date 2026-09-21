"""
Integration test: jalankan full pipeline Python (tanpa LLM dan Telegram).
Verifikasi data mengalir benar dari DataFetcher → NetCalc → Projection → Risk → Decision.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langflow.components.data_fetcher import fetch_store_data
from langflow.components.net_calculator import calculate_net
from langflow.components.projection_builder import build_projection
from langflow.components.risk_classifier import classify_risk
from langflow.components.decision_engine import make_decision


def run_pipeline(scenario: str) -> dict:
    raw = fetch_store_data("toko_andi_001", scenario)
    net = calculate_net(raw)
    proj = build_projection(net)
    risk = classify_risk(proj)
    decision = make_decision(risk)
    return decision


class TestIntegrationPipeline:
    def test_s1_aman(self):
        result = run_pipeline("S1_AMAN")
        assert result["status"] == "AMAN"
        assert result["current_cash"] == 4_200_000
        assert len(result["settlements"]) == 1

    def test_s2_waspada(self):
        result = run_pipeline("S2_WASPADA")
        assert result["status"] in ("WASPADA", "AMAN")  # tergantung tanggal saat test
        assert result["pending_decision"] is not None  # ada kebutuhan restock

    def test_s3_kritis(self):
        result = run_pipeline("S3_KRITIS")
        assert result["status"] == "KRITIS"
        assert result["current_cash"] == 850_000
        # Harus rekomendasikan tagih piutang
        assert result["pending_decision"]["type"] == "collect_receivable"
        assert result["pending_decision"]["target"] == "Toko Makmur"

    def test_s5_multi_settlement(self):
        result = run_pipeline("S5_MULTI_SETTLEMENT")
        # Harus ada 2 settlement individual — bukan digabung
        assert len(result["settlements"]) == 2
        marketplaces = {s["marketplace"] for s in result["settlements"]}
        assert "shopee" in marketplaces
        assert "tokopedia" in marketplaces

    def test_semua_skenario_tidak_crash(self):
        scenarios = ["S1_AMAN", "S2_WASPADA", "S3_KRITIS", "S4_RESTOCK_AMAN", "S5_MULTI_SETTLEMENT"]
        for s in scenarios:
            result = run_pipeline(s)
            assert "status" in result
            assert "current_cash" in result
            assert result["status"] in ("AMAN", "WASPADA", "KRITIS")