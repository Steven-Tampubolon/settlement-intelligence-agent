"""
Layer 3A — Decision Engine
BOLEH: Rules-based decision — restock timing, tagih piutang
TIDAK BOLEH: Probabilistic decision, memanggil LLM untuk keputusan
"""
from datetime import date, datetime
from langflow.custom import CustomComponent


class DecisionEngine(CustomComponent):
    display_name = "Decision Engine"
    description = "Tentukan rekomendasi aksi berdasarkan rules deterministik"

    def build_config(self):
        return {
            "risk_data": {
                "display_name": "Risk Classifier Output",
                "required": True,
            }
        }

    def build(self, risk_data: dict) -> dict:
        return make_decision(risk_data)


# ── Fungsi standalone ─────────────────────────────────────────────────
def make_decision(risk_data: dict) -> dict:
    """
    Rules:
    1. Jika KRITIS dan ada piutang jatuh tempo → rekomendasikan tagih piutang
    2. Jika ada kebutuhan restock → cek apakah ada settlement sebelum stok habis
    3. Jika tidak ada masalah khusus → rekomendasikan pantau saja
    """
    pending_decision = None
    status = risk_data["status"]

    # Rule 1: KRITIS + ada piutang → prioritas tagih dulu
    overdue = risk_data.get("overdue_receivables", [])
    if status == "KRITIS" and overdue:
        # Urutkan dari yang paling lama jatuh tempo
        sorted_overdue = sorted(overdue, key=lambda x: x["overdue_days"], reverse=True)
        top_receivable = sorted_overdue[0]
        pending_decision = {
            "type": "collect_receivable",
            "target": top_receivable["buyer"],
            "amount": top_receivable["amount"],
            "overdue_days": top_receivable["overdue_days"],
            "recommendation": (
                f"Tagih {top_receivable['buyer']} hari ini — "
                f"piutang Rp {top_receivable['amount']:,} telat {top_receivable['overdue_days']} hari"
            ).replace(",", "."),
            "all_receivables": sorted_overdue,
        }

    # Rule 2: Ada kebutuhan restock (override Rule 1 hanya jika bukan KRITIS)
    stock_need = risk_data.get("pending_stock_need")
    if stock_need and status != "KRITIS":
        best_settlement = _find_settlement_before(
            risk_data["settlements_net"],
            stock_need["stock_depletes_on"],
        )
        pending_decision = _build_restock_decision(best_settlement, stock_need, status)

    # Rule 3: Multi-settlement WASPADA + restock + piutang → gabungkan info
    if stock_need and overdue and status == "WASPADA":
        pending_decision = {
            "type": "multi_action",
            "restock": _build_restock_decision(
                _find_settlement_before(
                    risk_data["settlements_net"],
                    stock_need["stock_depletes_on"],
                ),
                stock_need,
                status,
            ),
            "receivables": overdue,
            "recommendation": "Monitor settlement masuk, selesaikan piutang paralel",
        }

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


def _find_settlement_before(settlements: list, deadline_str: str) -> dict | None:
    """Cari settlement pertama yang cair SEBELUM deadline."""
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

    # Ambil yang paling awal cair
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _build_restock_decision(
    best_settlement: dict | None,
    stock_need: dict,
    status: str,
) -> dict:
    """Bangun objek keputusan restock berdasarkan rules."""
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
                f"({disburse_date}) — dana cukup Rp {net:,}".replace(",", ".")
            )
        else:
            shortfall = cost - net
            recommendation = (
                f"Restock {item} butuh Rp {cost:,} — "
                f"settlement {mkt} hanya Rp {net:,}, "
                f"kurang Rp {shortfall:,}. Cari sumber dana tambahan.".replace(",", ".")
            )
    else:
        recommendation = (
            f"Tidak ada settlement sebelum stok {item} habis ({depletes}). "
            f"Pertimbangkan pinjaman atau tunda restock."
        )

    return {
        "type": "restock",
        "item": item,
        "cost": cost,
        "stock_depletes": depletes,
        "best_settlement": best_settlement,
        "recommendation": recommendation,
    }