import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langflow.logic.net_calculator import calculate_net


def _make_raw(settlements, cash=4200000, expense=800000):
    return {
        "store_id": "test_001",
        "owner_name": "Test Owner",
        "current_cash_balance": cash,
        "average_daily_expense": expense,
        "settlements": settlements,
        "overdue_receivables": [],
        "pending_stock_need": None,
    }


class TestNetCalculator:
    def test_single_settlement_basic(self):
        raw = _make_raw([{
            "settlement_id": "SPJ-001",
            "marketplace": "shopee",
            "gross_revenue": 12_400_000,
            "commission_rate": 0.05,
            "admin_fee": 150_000,
            "shipping_subsidy": 280_000,
            "returns_total": 340_000,
            "scheduled_disbursement_date": "2026-09-24",
            "status": "pending",
        }])
        result = calculate_net(raw)

        s = result["settlements_net"][0]
        # gross 12.4jt * 0.05 komisi = 620.000
        # net = 12.400.000 - 620.000 - 150.000 - 280.000 - 340.000 = 11.010.000
        assert s["net_amount"] == 11_010_000
        assert s["breakdown"]["commission"] == 620_000
        assert s["marketplace"] == "shopee"
        assert result["total_net_incoming"] == 11_010_000

    def test_multi_settlement(self):
        raw = _make_raw([
            {
                "settlement_id": "SPJ-501",
                "marketplace": "shopee",
                "gross_revenue": 14_500_000,
                "commission_rate": 0.05,
                "admin_fee": 150_000,
                "shipping_subsidy": 300_000,
                "returns_total": 250_000,
                "scheduled_disbursement_date": "2026-09-24",
                "status": "pending",
            },
            {
                "settlement_id": "TPJ-501",
                "marketplace": "tokopedia",
                "gross_revenue": 8_000_000,
                "commission_rate": 0.055,
                "admin_fee": 100_000,
                "shipping_subsidy": 180_000,
                "returns_total": 120_000,
                "scheduled_disbursement_date": "2026-09-25",
                "status": "pending",
            },
        ])
        result = calculate_net(raw)

        assert len(result["settlements_net"]) == 2
        shopee_net = next(s for s in result["settlements_net"] if s["marketplace"] == "shopee")
        tokped_net = next(s for s in result["settlements_net"] if s["marketplace"] == "tokopedia")

        # shopee: 14.5jt - 725.000 - 150.000 - 300.000 - 250.000 = 13.075.000
        assert shopee_net["net_amount"] == 13_075_000
        # tokped: 8jt - 440.000 - 100.000 - 180.000 - 120.000 = 7.160.000
        assert tokped_net["net_amount"] == 7_160_000
        assert result["total_net_incoming"] == 13_075_000 + 7_160_000

    def test_zero_returns(self):
        raw = _make_raw([{
            "settlement_id": "SPJ-ZR",
            "marketplace": "shopee",
            "gross_revenue": 5_000_000,
            "commission_rate": 0.05,
            "admin_fee": 0,
            "shipping_subsidy": 0,
            "returns_total": 0,
            "scheduled_disbursement_date": "2026-09-24",
            "status": "pending",
        }])
        result = calculate_net(raw)
        # net = 5.000.000 - 250.000 = 4.750.000
        assert result["settlements_net"][0]["net_amount"] == 4_750_000

    def test_passthrough_fields(self):
        """Field dari raw_data harus tersedia di output untuk komponen berikutnya."""
        raw = _make_raw(
            settlements=[{
                "settlement_id": "X",
                "marketplace": "shopee",
                "gross_revenue": 1_000_000,
                "commission_rate": 0.05,
                "admin_fee": 0,
                "shipping_subsidy": 0,
                "returns_total": 0,
                "scheduled_disbursement_date": "2026-09-24",
                "status": "pending",
            }],
            cash=3_000_000,
            expense=500_000,
        )
        result = calculate_net(raw)
        assert result["current_cash_balance"] == 3_000_000
        assert result["average_daily_expense"] == 500_000
        assert result["owner_name"] == "Test Owner"