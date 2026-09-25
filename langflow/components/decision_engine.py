import json
from datetime import datetime
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema.message import Message

# Konstanta threshold — sesuai ARCHITECTURE_BOUNDARIES
FLASH_SALE_MIN_CASH_BUFFER = 2_000_000
FLASH_SALE_MAX_STOCK_BUDGET_RATIO = 0.5


class DecisionEngine(Component):
    display_name = "Decision Engine"
    description = "Tentukan rekomendasi aksi berdasarkan rules deterministik"

    inputs = [
        DataInput(name="risk_data", display_name="Risk Classifier Output", required=True),
    ]

    outputs = [
        Output(display_name="Decision Data (JSON)", name="decision_data", method="decide"),
    ]

    def decide(self) -> Message:
        result = self._make_decision(self.risk_data.data)
        self.status = result
        return Message(text=json.dumps(result, ensure_ascii=False))

    def _make_decision(self, risk_data: dict) -> dict:
        status = risk_data["status"]
        overdue = risk_data.get("overdue_receivables", [])
        stock_need = risk_data.get("pending_stock_need")
        flash_sale_opportunity = risk_data.get("flash_sale_opportunity")

        active_decisions = []

        # Rule 1: ada piutang jatuh tempo (semua status)
        if overdue:
            active_decisions.append(self._build_collect_receivable(overdue))

        # Rule 2: ada kebutuhan restock
        if stock_need:
            best = self._find_settlement_before(
                risk_data["settlements_net"], stock_need["stock_depletes_on"]
            )
            active_decisions.append(self._build_restock(best, stock_need, status))

        # Rule 3: AMAN + ada peluang flash sale
        if flash_sale_opportunity and status == "AMAN":
            active_decisions.append(
                self._evaluate_flash_sale(risk_data, flash_sale_opportunity)
            )

        if len(active_decisions) == 0:
            pending_decision = None
        elif len(active_decisions) == 1:
            pending_decision = active_decisions[0]
        else:
            pending_decision = self._build_multiple(active_decisions)

        return {
            "store_owner": risk_data["owner_name"],
            "store_id": risk_data["store_id"],
            "status": status,
            "urgency_level": risk_data["urgency_level"],
            "current_cash": risk_data["current_cash_balance"],
            "runway_days": risk_data["runway_days"],
            "min_balance_amount": risk_data["min_balance_amount"],
            "settlements": risk_data["settlements_net"],
            "total_incoming_this_week": risk_data["total_net_incoming"],
            "pending_decision": pending_decision,
            "daily_projection": risk_data["daily_projection"],
        }

    def _build_collect_receivable(self, overdue: list) -> dict:
        sorted_overdue = sorted(overdue, key=lambda x: x["overdue_days"], reverse=True)
        top = sorted_overdue[0]
        return {
            "type": "collect_receivable",
            "target": top["buyer"],
            "amount": top["amount"],
            "overdue_days": top["overdue_days"],
            "recommendation": (
                f"Tagih {top['buyer']} hari ini — "
                f"piutang Rp {top['amount']:,} telat {top['overdue_days']} hari"
            ).replace(",", "."),
            "all_receivables": sorted_overdue,
        }

    def _evaluate_flash_sale(self, risk_data: dict, opportunity: dict) -> dict:
        current_cash = risk_data["current_cash_balance"]
        stock_budget = opportunity["required_stock_budget"]
        cash_after = current_cash - stock_budget
        can_join = (
            cash_after >= FLASH_SALE_MIN_CASH_BUFFER
            and stock_budget <= current_cash * FLASH_SALE_MAX_STOCK_BUDGET_RATIO
        )
        if can_join:
            recommendation = (
                f"IKUT flash sale {opportunity['platform']} — "
                f"kas tetap aman (sisa Rp {cash_after:,})"
            ).replace(",", ".")
        else:
            recommendation = (
                f"TUNGGU dulu — ikut flash sale akan menyisakan kas hanya "
                f"Rp {cash_after:,}, terlalu tipis"
            ).replace(",", ".")
        return {
            "type": "flash_sale",
            "platform": opportunity["platform"],
            "date": opportunity["date"],
            "estimated_revenue_uplift": opportunity["estimated_revenue_uplift"],
            "required_stock_budget": stock_budget,
            "cash_after_joining": cash_after,
            "can_join": can_join,
            "recommendation": recommendation,
        }

    def _build_multiple(self, decisions: list) -> dict:
        priority_order = {"collect_receivable": 0, "restock": 1, "flash_sale": 2}
        sorted_decisions = sorted(
            decisions, key=lambda d: priority_order.get(d["type"], 99)
        )
        result = {"type": "multiple", "decisions": sorted_decisions}
        for i, d in enumerate(sorted_decisions, start=1):
            result[f"priority_{i}"] = d["recommendation"]
        return result

    def _find_settlement_before(self, settlements: list, deadline_str: str):
        try:
            deadline = datetime.fromisoformat(deadline_str).date()
        except ValueError:
            return None
        candidates = []
        for s in settlements:
            try:
                d = datetime.fromisoformat(s["disbursement_date"]).date()
                if d <= deadline:
                    candidates.append((d, s))
            except ValueError:
                continue
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def _build_restock(self, best_settlement, stock_need: dict, status: str) -> dict:
        item = stock_need["item"]
        cost = stock_need["estimated_cost"]
        depletes = stock_need["stock_depletes_on"]
        if best_settlement:
            net = best_settlement["net_amount"]
            mkt = best_settlement["marketplace"]
            disburse_date = best_settlement["disbursement_date"]
            if net >= cost:
                recommendation = (
                    f"Restock {item} setelah settlement {mkt} cair "
                    f"({disburse_date}) — dana cukup Rp {net:,}"
                ).replace(",", ".")
            else:
                shortfall = cost - net
                recommendation = (
                    f"Restock {item} butuh Rp {cost:,} — "
                    f"settlement {mkt} hanya Rp {net:,}, "
                    f"kurang Rp {shortfall:,}"
                ).replace(",", ".")
        else:
            recommendation = (
                f"Tidak ada settlement sebelum stok {item} habis ({depletes}). "
                f"Pertimbangkan pinjaman."
            )
        return {
            "type": "restock",
            "item": item,
            "cost": cost,
            "stock_depletes": depletes,
            "best_settlement": best_settlement,
            "recommendation": recommendation,
        }

    def build(self):
        return self.decide