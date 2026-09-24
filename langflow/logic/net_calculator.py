def calculate_net(raw_data: dict) -> dict:
    settlements_net = []
    total_net = 0
    for s in raw_data["settlements"]:
        gross = s["gross_revenue"]
        commission = gross * s["commission_rate"]
        admin_fee = s["admin_fee"]
        shipping_subsidy = s["shipping_subsidy"]
        returns = s["returns_total"]
        net = round(gross - commission - admin_fee - shipping_subsidy - returns)
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
        "overdue_receivables": raw_data.get("overdue_receivables", []),
        "pending_stock_need": raw_data.get("pending_stock_need"),
        "flash_sale_opportunity": raw_data.get("flash_sale_opportunity"),
    }