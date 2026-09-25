import json
from datetime import date, timedelta
from pathlib import Path


def fetch_store_data(store_id: str, scenario: str = "S1_AMAN") -> dict:
    mock_data_path = (
        Path(__file__).parent.parent / "mock_data" / "store_scenarios.json"
    )
    with open(mock_data_path, "r", encoding="utf-8") as f:
        all_scenarios = json.load(f)
    if scenario not in all_scenarios["scenarios"]:
        raise ValueError(f"Scenario '{scenario}' tidak ditemukan.")
    data = all_scenarios["scenarios"][scenario]["data"].copy()
    data["store_id"] = store_id
    data = _adjust_dates(data)
    return data


def _adjust_dates(data: dict) -> dict:
    """
    Adjust semua tanggal di mock data agar relatif ke hari ini.
    Ini mencegah test gagal karena tanggal settlement sudah lewat.

    Referensi tanggal asli di mock data: 2026-09-21 (tanggal spike test)
    Offset dihitung dari tanggal tersebut ke hari ini.
    """
    MOCK_BASE_DATE = date(2026, 9, 21)
    today = date.today()
    delta_days = (today - MOCK_BASE_DATE).days

    def shift_date(date_str: str) -> str:
        try:
            d = date.fromisoformat(date_str)
            return str(d + timedelta(days=delta_days))
        except (ValueError, TypeError):
            return date_str

    # Adjust settlement dates
    for s in data.get("settlements", []):
        if "scheduled_disbursement_date" in s:
            s["scheduled_disbursement_date"] = shift_date(
                s["scheduled_disbursement_date"]
            )

    # Adjust stock depletes date
    stock = data.get("pending_stock_need")
    if stock and "stock_depletes_on" in stock:
        stock["stock_depletes_on"] = shift_date(stock["stock_depletes_on"])

    # Adjust flash sale date
    flash = data.get("flash_sale_opportunity")
    if flash and "date" in flash:
        flash["date"] = shift_date(flash["date"])

    return data