from datetime import date, timedelta
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.data import Data


class ProjectionBuilder(Component):
    display_name = "Projection Builder"
    description = "Bangun proyeksi saldo kas harian H+0 hingga H+14"

    inputs = [
        DataInput(name="net_data", display_name="Net Calculator Output", required=True),
    ]

    outputs = [
        Output(display_name="Projection", name="projection", method="project"),
    ]

    def project(self) -> Data:
        result = self._build_projection(self.net_data.data)
        self.status = result
        return Data(data=result)

    def _build_projection(self, net_data: dict, reference_date=None) -> dict:
        if reference_date is None:
            reference_date = date.today()
        incoming_by_date = {}
        for s in net_data["settlements_net"]:
            d = s["disbursement_date"]
            incoming_by_date[d] = incoming_by_date.get(d, 0) + s["net_amount"]
        balance = net_data["current_cash_balance"]
        daily_expense = net_data["average_daily_expense"]
        projection = []
        runway_days = 14
        for i in range(15):
            current_date = reference_date + timedelta(days=i)
            date_str = str(current_date)
            incoming_today = incoming_by_date.get(date_str, 0)
            if i > 0:
                balance = balance - daily_expense + incoming_today
            else:
                balance = balance + incoming_today
            balance = round(balance)
            projection.append({
                "date": date_str,
                "day_offset": i,
                "projected_balance": balance,
                "incoming_today": incoming_today,
            })
            if balance <= 0 and runway_days == 14:
                runway_days = i
        min_day = min(projection, key=lambda x: x["projected_balance"])
        return {
            "daily_projection": projection,
            "runway_days": runway_days,
            "min_balance_amount": min_day["projected_balance"],
            "min_balance_day": min_day["date"],
            "settlements_net": net_data["settlements_net"],
            "total_net_incoming": net_data["total_net_incoming"],
            "current_cash_balance": net_data["current_cash_balance"],
            "average_daily_expense": net_data["average_daily_expense"],
            "owner_name": net_data["owner_name"],
            "store_id": net_data["store_id"],
            "overdue_receivables": net_data.get("overdue_receivables", []),
            "pending_stock_need": net_data.get("pending_stock_need"),
            "flash_sale_opportunity": net_data.get("flash_sale_opportunity"),
        }

    def build(self):
        return self.project