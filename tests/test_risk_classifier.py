import pytest
import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from langflow.logic.risk_classifier import classify_risk, CRITICAL_THRESHOLD_DAYS, WARNING_THRESHOLD_DAYS


def _make_projection(runway_days, min_balance=100_000):
    today = date.today()
    return {
        "runway_days": runway_days,
        "min_balance_amount": min_balance,
        "min_balance_day": str(today + timedelta(days=runway_days)),
        "daily_projection": [],
        "settlements_net": [],
        "total_net_incoming": 0,
        "current_cash_balance": 1_000_000,
        "average_daily_expense": 500_000,
        "owner_name": "Test",
        "store_id": "test_001",
        "overdue_receivables": [],
        "pending_stock_need": None,
    }


class TestRiskClassifier:
    def test_kritis_batas_bawah(self):
        result = classify_risk(_make_projection(runway_days=1))
        assert result["status"] == "KRITIS"
        assert result["urgency_level"] == 3

    def test_kritis_tepat_threshold(self):
        result = classify_risk(_make_projection(runway_days=CRITICAL_THRESHOLD_DAYS))
        assert result["status"] == "KRITIS"

    def test_waspada_satu_diatas_kritis(self):
        result = classify_risk(_make_projection(runway_days=CRITICAL_THRESHOLD_DAYS + 1))
        assert result["status"] == "WASPADA"
        assert result["urgency_level"] == 2

    def test_waspada_tepat_threshold(self):
        result = classify_risk(_make_projection(runway_days=WARNING_THRESHOLD_DAYS))
        assert result["status"] == "WASPADA"

    def test_aman(self):
        result = classify_risk(_make_projection(runway_days=WARNING_THRESHOLD_DAYS + 1))
        assert result["status"] == "AMAN"
        assert result["urgency_level"] == 1

    def test_aman_14_hari(self):
        result = classify_risk(_make_projection(runway_days=14))
        assert result["status"] == "AMAN"