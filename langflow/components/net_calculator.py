"""
Layer 3A — Net Calculator
BOLEH: Kalkulasi net settlement per marketplace
TIDAK BOLEH: Natural language, keputusan, memanggil LLM
"""
from datetime import date
from langflow.custom import CustomComponent


class NetCalculator(CustomComponent):
    display_name = "Net Calculator"
    description = "Hitung net settlement: gross - komisi - admin - ongkir subsidi - retur"

    def build_config(self):
        return {
            "raw_data": {
                "display_name": "Raw Store Data",
                "info": "Output dari Data Fetcher",
                "required": True,
            }
        }

    def build(self, raw_data: dict) -> dict:
        return calculate_net(raw_data)


# ── Fungsi standalone ─────────────────────────────────────────────────
def calculate_net(raw_data: dict) -> dict:
    """
    Hitung net amount per settlement.

    Formula: net = gross - komisi - admin_fee - shipping_subsidy - returns

    Catatan: shipping_subsidy adalah subsidi ongkir yang KITA bayar ke platform
    (bukan yang diterima), sehingga mengurangi net.
    """
    settlements_net = []
    total_net = 0

    for s in raw_data["settlements"]:
        gross = s["gross_revenue"]
        commission = gross * s["commission_rate"]
        admin_fee = s["admin_fee"]
        shipping_subsidy = s["shipping_subsidy"]
        returns = s["returns_total"]

        net = gross - commission - admin_fee - shipping_subsidy - returns
        net = round(net)  # bulatkan ke rupiah terdekat

        settlements_net.append({
            "settlement_id": s["settlement_id"],
            "marketplace": s["marketplace"],
            "gross_revenue": gross,
            "net_amount": net,
            "disbursement_date": s["scheduled_disbursement_date"],
            "breakdown": {
                "commission": round(commission),
                "admin_fee": admin_fee,
                "shipping_subsidy": shipping_subsidy,
                "returns": returns,
                "total_deductions": round(gross - net),
            },
        })
        total_net += net

    return {
        "settlements_net": settlements_net,
        "total_net_incoming": round(total_net),
        "current_cash_balance": raw_data["current_cash_balance"],
        "average_daily_expense": raw_data["average_daily_expense"],
        "owner_name": raw_data["owner_name"],
        "store_id": raw_data["store_id"],
        # Pass-through untuk komponen berikutnya
        "overdue_receivables": raw_data.get("overdue_receivables", []),
        "pending_stock_need": raw_data.get("pending_stock_need"),
    }