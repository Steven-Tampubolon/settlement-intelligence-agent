from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data

CRITICAL_THRESHOLD_DAYS = 3
WARNING_THRESHOLD_DAYS = 7


class RiskClassifier(Component):
    display_name = "Risk Classifier"
    description = "Klasifikasi risiko berdasarkan runway kas (threshold tetap)"

    inputs = [
        DataInput(name="projection", display_name="Projection Builder Output", required=True),
    ]

    outputs = [
        Output(display_name="Risk Data", name="risk_data", method="classify"),
    ]

    def classify(self) -> Data:
        result = self._classify_risk(self.projection.data)
        self.status = result
        return Data(data=result)

    def _classify_risk(self, projection: dict) -> dict:
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
            "daily_projection": projection["daily_projection"],
            "settlements_net": projection["settlements_net"],
            "total_net_incoming": projection["total_net_incoming"],
            "current_cash_balance": projection["current_cash_balance"],
            "average_daily_expense": projection["average_daily_expense"],
            "owner_name": projection["owner_name"],
            "store_id": projection["store_id"],
            "overdue_receivables": projection.get("overdue_receivables", []),
            "pending_stock_need": projection.get("pending_stock_need"),
            "flash_sale_opportunity": projection.get("flash_sale_opportunity"),
        }

    def build(self):
        return self.classify