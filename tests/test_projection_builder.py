import pytest
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from langflow.logic.projection_builder import build_projection


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
        Kas 1jt, expense 500k/hari → habis H+2 tanpa bantuan.
        Tapi ada settlement 5jt di H+1 → kas bertahan lebih lama.

        Trace:
        H+0: 1.000.000 (tidak dikurangi expense di H+0)
        H+1: 1.000.000 - 500.000 + 5.000.000 = 5.500.000
        H+2 s/d H+12: -500.000/hari → saldo 0 tepat di H+12

        Jadi runway_days = 12 (pertama kali saldo <= 0 di H+12).
        Yang penting: JAUH lebih baik dari tanpa settlement (runway = 2).
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

        # Settlement menyelamatkan kas: runway jauh lebih panjang dari tanpa settlement (2 hari)
        assert result["runway_days"] > 2, "Settlement seharusnya memperpanjang runway"
        assert result["runway_days"] == 12  # hasil kalkulasi yang benar

        # Verifikasi saldo di H+1 benar (settlement masuk)
        h1 = result["daily_projection"][1]
        assert h1["projected_balance"] == 5_500_000
        assert h1["incoming_today"] == 5_000_000

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