import pytest
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from langflow.components.projection_builder import build_projection


def _make_net_data(cash, expense, settlements):
    return {
        "current_cash_balance": cash,
        "average_daily_expense": expense,
        "settlements_net": settlements,
        "total_net_incoming": sum(s["net_amount"] for s in settlements),
        "owner_name": "Test",
        "store_id": "test_001",
        "overdue_receivables": [],
        "pending_stock_need": None,
    }


class TestProjectionBuilder:
    def test_no_incoming_kas_habis(self):
        """Kas 3jt, expense 1jt/hari, tidak ada settlement → habis di H+3."""
        today = date.today()
        net_data = _make_net_data(3_000_000, 1_000_000, [])
        result = build_projection(net_data, reference_date=today)

        assert result["runway_days"] == 3
        assert result["min_balance_amount"] <= 0

    def test_settlement_menyelamatkan_kas(self):
        """
        Kas 1jt, expense 500k/hari → habis H+2.
        Tapi ada settlement 5jt di H+1 → kas aman.
        """
        today = date.today()
        from datetime import timedelta
        disburse = str(today + timedelta(days=1))

        net_data = _make_net_data(
            cash=1_000_000,
            expense=500_000,
            settlements=[{
                "settlement_id": "X",
                "marketplace": "shopee",
                "net_amount": 5_000_000,
                "disbursement_date": disburse,
            }]
        )
        result = build_projection(net_data, reference_date=today)
        assert result["runway_days"] == 14  # tidak pernah minus dalam 14 hari

    def test_14_hari_output(self):
        """Proyeksi selalu menghasilkan 15 titik data (H+0 hingga H+14)."""
        net_data = _make_net_data(10_000_000, 100_000, [])
        result = build_projection(net_data)
        assert len(result["daily_projection"]) == 15

    def test_kas_aman_runway_14(self):
        """Kas sangat besar, tidak pernah minus → runway 14."""
        net_data = _make_net_data(100_000_000, 500_000, [])
        result = build_projection(net_data)
        assert result["runway_days"] == 14