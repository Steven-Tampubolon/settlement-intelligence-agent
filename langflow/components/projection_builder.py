"""
Layer 3A — Projection Builder
BOLEH: Susun proyeksi kas H+0 s/d H+14 berdasarkan jadwal disbursement
TIDAK BOLEH: Estimasi probabilistik, natural language, memanggil LLM
"""
from datetime import date, timedelta, datetime
from langflow.custom import CustomComponent


class ProjectionBuilder(CustomComponent):
    display_name = "Projection Builder"
    description = "Bangun proyeksi saldo kas harian H+0 hingga H+14"

    def build_config(self):
        return {
            "net_data": {
                "display_name": "Net Calculator Output",
                "required": True,
            }
        }

    def build(self, net_data: dict) -> dict:
        return build_projection(net_data)


# ── Fungsi standalone ─────────────────────────────────────────────────
def build_projection(net_data: dict, reference_date: date | None = None) -> dict:
    """
    Proyeksikan saldo kas untuk 14 hari ke depan.

    - Setiap hari dikurangi average_daily_expense
    - Pada hari disbursement, tambahkan net settlement
    - runway_days = hari pertama saldo jadi <= 0 (atau 14 jika tidak terjadi)
    """
    if reference_date is None:
        reference_date = date.today()

    # Buat lookup: tanggal → total dana masuk hari itu
    incoming_by_date: dict[str, float] = {}
    for s in net_data["settlements_net"]:
        d = s["disbursement_date"]
        incoming_by_date[d] = incoming_by_date.get(d, 0) + s["net_amount"]

    balance = net_data["current_cash_balance"]
    daily_expense = net_data["average_daily_expense"]
    projection = []
    runway_days = 14  # default: aman sampai akhir window

    for i in range(15):  # H+0 sampai H+14
        current_date = reference_date + timedelta(days=i)
        date_str = str(current_date)

        # Dana masuk hari ini (jika ada disbursement)
        incoming_today = incoming_by_date.get(date_str, 0)

        # H+0 tidak dikurangi expense lagi (sudah spent hari ini)
        if i > 0:
            balance = balance - daily_expense + incoming_today
        else:
            balance = balance + incoming_today  # H+0: hanya tambah jika ada disbursement hari ini

        balance = round(balance)

        projection.append({
            "date": date_str,
            "day_offset": i,
            "projected_balance": balance,
            "incoming_today": incoming_today,
        })

        # Catat pertama kali saldo <= 0
        if balance <= 0 and runway_days == 14:
            runway_days = i

    # Cari hari dengan saldo minimum
    min_day = min(projection, key=lambda x: x["projected_balance"])

    return {
        "daily_projection": projection,
        "runway_days": runway_days,
        "min_balance_amount": min_day["projected_balance"],
        "min_balance_day": min_day["date"],
        # Pass-through
        "settlements_net": net_data["settlements_net"],
        "total_net_incoming": net_data["total_net_incoming"],
        "current_cash_balance": net_data["current_cash_balance"],
        "average_daily_expense": net_data["average_daily_expense"],
        "owner_name": net_data["owner_name"],
        "store_id": net_data["store_id"],
        "overdue_receivables": net_data.get("overdue_receivables", []),
        "pending_stock_need": net_data.get("pending_stock_need"),
    }