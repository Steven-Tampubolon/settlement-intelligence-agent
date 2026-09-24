CRITICAL_THRESHOLD_DAYS = 3
WARNING_THRESHOLD_DAYS = 7


def classify_risk(projection: dict) -> dict:
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