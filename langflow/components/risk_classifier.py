"""
Layer 3A — Risk Classifier
BOLEH: Klasifikasi AMAN/WASPADA/KRITIS berdasarkan threshold TETAP
TIDAK BOLEH: Judgment probabilistik, threshold di prompt LLM
"""
from langflow.custom import CustomComponent


# ── KONSTANTA — jangan pindahkan ke prompt atau config Langflow ────────
CRITICAL_THRESHOLD_DAYS = 3
WARNING_THRESHOLD_DAYS = 7


class RiskClassifier(CustomComponent):
    display_name = "Risk Classifier"
    description = "Klasifikasi risiko berdasarkan runway kas (threshold tetap)"

    def build_config(self):
        return {
            "projection": {
                "display_name": "Projection Builder Output",
                "required": True,
            }
        }

    def build(self, projection: dict) -> dict:
        return classify_risk(projection)


# ── Fungsi standalone ─────────────────────────────────────────────────
def classify_risk(projection: dict) -> dict:
    """
    Klasifikasi berdasarkan runway_days.

    KRITIS  : runway <= 3 hari
    WASPADA : runway <= 7 hari
    AMAN    : runway > 7 hari
    """
    runway = projection["runway_days"]

    if runway <= CRITICAL_THRESHOLD_DAYS:
        status = "KRITIS"
        urgency_level = 3
    elif runway <= WARNING_THRESHOLD_DAYS:
        status = "WASPADA"
        urgency_level = 2
    else:
        status = "AMAN"
        urgency_level = 1

    return {
        "status": status,
        "urgency_level": urgency_level,
        "runway_days": runway,
        "min_balance_amount": projection["min_balance_amount"],
        "min_balance_day": projection["min_balance_day"],
        # Pass-through semua data yang dibutuhkan Decision Engine
        "daily_projection": projection["daily_projection"],
        "settlements_net": projection["settlements_net"],
        "total_net_incoming": projection["total_net_incoming"],
        "current_cash_balance": projection["current_cash_balance"],
        "average_daily_expense": projection["average_daily_expense"],
        "owner_name": projection["owner_name"],
        "store_id": projection["store_id"],
        "overdue_receivables": projection.get("overdue_receivables", []),
        "pending_stock_need": projection.get("pending_stock_need"),
    }