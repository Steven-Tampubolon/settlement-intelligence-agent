"""
Integration test: jalankan full pipeline Python (tanpa LLM dan Telegram).
Verifikasi data mengalir benar dari DataFetcher → NetCalc → Projection → Risk → Decision.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langflow.logic.data_fetcher import fetch_store_data
from langflow.logic.net_calculator import calculate_net
from langflow.logic.projection_builder import build_projection
from langflow.logic.risk_classifier import classify_risk
from langflow.logic.decision_engine import make_decision


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

    def test_s6_flash_sale_can_join(self):
        """S6: kas cukup, flash sale layak diikuti."""
        raw = fetch_store_data("toko_andi_001", "S6_FLASH_SALE")
        net = calculate_net(raw)
        proj = build_projection(net)
        risk = classify_risk(proj)
        result = make_decision(risk)

        assert result["status"] == "AMAN"
        assert result["pending_decision"] is not None
        assert result["pending_decision"]["type"] == "flash_sale"
        assert result["pending_decision"]["can_join"] is True
        assert result["pending_decision"]["cash_after_joining"] == 12400000 - 4500000
        assert "IKUT" in result["pending_decision"]["recommendation"]


    def test_s6_flash_sale_cannot_join(self):
        """Variasi S6: kas terlalu tipis setelah ikut flash sale."""
        from langflow.logic.decision_engine import _evaluate_flash_sale

        risk_data = {
            "current_cash_balance": 5000000,
            "settlements_net": [],
            "overdue_receivables": [],
            "pending_stock_need": None,
        }
        opportunity = {
            "platform": "Tokopedia",
            "date": "2026-09-23",
            "estimated_revenue_uplift": 5000000,
            "required_stock_budget": 3500000,  # cash_after = 1.500.000 < 2.000.000 buffer
        }
        decision = _evaluate_flash_sale(risk_data, opportunity)

        assert decision["type"] == "flash_sale"
        assert decision["can_join"] is False
        assert "TUNGGU" in decision["recommendation"]
        assert decision["cash_after_joining"] == 5000000 - 3500000