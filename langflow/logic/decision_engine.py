from datetime import datetime


def make_decision(risk_data: dict) -> dict:
    pending_decision = None
    status = risk_data["status"]
    overdue = risk_data.get("overdue_receivables", [])
    if status == "KRITIS" and overdue:
        sorted_overdue = sorted(overdue, key=lambda x: x["overdue_days"], reverse=True)
        top = sorted_overdue[0]
        pending_decision = {
            "type": "collect_receivable",
            "target": top["buyer"],
            "amount": top["amount"],
            "overdue_days": top["overdue_days"],
            "recommendation": f"Tagih {top['buyer']} hari ini — piutang Rp {top['amount']:,} telat {top['overdue_days']} hari".replace(",", "."),
            "all_receivables": sorted_overdue,
        }
    stock_need = risk_data.get("pending_stock_need")
    if stock_need and status != "KRITIS":
        best = _find_settlement_before(risk_data["settlements_net"], stock_need["stock_depletes_on"])
        pending_decision = _build_restock_decision(best, stock_need, status)
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


def _find_settlement_before(settlements, deadline_str):
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


def _build_restock_decision(best_settlement, stock_need, status):
    item = stock_need["item"]
    cost = stock_need["estimated_cost"]
    depletes = stock_need["stock_depletes_on"]
    if best_settlement:
        net = best_settlement["net_amount"]
        mkt = best_settlement["marketplace"]
        disburse_date = best_settlement["disbursement_date"]
        if net >= cost:
            recommendation = f"Restock {item} setelah settlement {mkt} cair ({disburse_date}) — dana cukup Rp {net:,}".replace(",", ".")
        else:
            shortfall = cost - net
            recommendation = f"Restock {item} butuh Rp {cost:,} — settlement {mkt} hanya Rp {net:,}, kurang Rp {shortfall:,}".replace(",", ".")
    else:
        recommendation = f"Tidak ada settlement sebelum stok {item} habis ({depletes}). Pertimbangkan pinjaman."
    return {
        "type": "restock",
        "item": item,
        "cost": cost,
        "stock_depletes": depletes,
        "best_settlement": best_settlement,
        "recommendation": recommendation,
    }