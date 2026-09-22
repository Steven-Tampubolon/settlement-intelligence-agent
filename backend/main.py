# backend/main.py
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from backend.config import validate_config, TELEGRAM_BOT_TOKEN, WEBHOOK_BASE_URL
from backend.database import init_db, seed_demo_store
from backend.scheduler.daily_monitor import run_daily_monitoring
from backend.services.telegram_webhook import build_telegram_app

import telegram

scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")
telegram_app = build_telegram_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_config()
    init_db()
    seed_demo_store()

    # Initialize telegram app
    await telegram_app.initialize()

    # Setup webhook jika URL tersedia
    if WEBHOOK_BASE_URL:
        webhook_url = f"{WEBHOOK_BASE_URL}/webhook/telegram"
        await telegram_app.bot.set_webhook(url=webhook_url)
        print(f"✅ Telegram webhook aktif: {webhook_url}")
    else:
        print("⚠️  WEBHOOK_BASE_URL tidak diset — webhook tidak aktif")

    # Start scheduler
    scheduler.add_job(
        run_daily_monitoring,
        "cron",
        hour=6,
        minute=0,
        id="daily_monitoring",
    )
    scheduler.start()
    print("✅ Scheduler aktif — monitoring harian 06:00 WIB")

    yield

    # Shutdown
    if WEBHOOK_BASE_URL:
        await telegram_app.bot.delete_webhook()
    await telegram_app.shutdown()
    scheduler.shutdown()


app = FastAPI(
    title="Settlement Intelligence Agent",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Webhook endpoint ───────────────────────────────────────────────────
@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Terima update dari Telegram dan proses via python-telegram-bot."""
    data = await request.json()
    update = telegram.Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}


# ── Endpoints lainnya ──────────────────────────────────────────────────
class TriggerRequest(BaseModel):
    store_id: str = "toko_andi_001"
    scenario: str = "S1_AMAN"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/trigger")
def trigger_now(req: TriggerRequest):
    import threading
    t = threading.Thread(
        target=run_daily_monitoring,
        kwargs={"scenario_override": req.scenario},
    )
    t.start()
    return {
        "status": "triggered",
        "store_id": req.store_id,
        "scenario": req.scenario,
        "message": "Cek Telegram Anda dalam beberapa detik.",
    }


@app.post("/trigger/scenario/{scenario}")
def trigger_scenario(scenario: str):
    valid_scenarios = ["S1_AMAN", "S2_WASPADA", "S3_KRITIS", "S4_RESTOCK_AMAN", "S5_MULTI_SETTLEMENT"]
    if scenario not in valid_scenarios:
        raise HTTPException(
            status_code=400,
            detail=f"Scenario tidak valid. Pilih dari: {valid_scenarios}"
        )
    import threading
    t = threading.Thread(
        target=run_daily_monitoring,
        kwargs={"scenario_override": scenario},
    )
    t.start()
    return {"status": "triggered", "scenario": scenario}


@app.post("/trigger/all-scenarios")
def trigger_all_scenarios():
    scenarios = ["S1_AMAN", "S2_WASPADA", "S3_KRITIS", "S4_RESTOCK_AMAN", "S5_MULTI_SETTLEMENT"]
    results = []
    for s in scenarios:
        try:
            run_daily_monitoring(scenario_override=s)
            results.append({"scenario": s, "status": "ok"})
        except Exception as e:
            results.append({"scenario": s, "status": "error", "error": str(e)})
    return {"results": results}


@app.get("/scheduler/status")
def scheduler_status():
    jobs = [{"id": job.id, "next_run": str(job.next_run_time)} for job in scheduler.get_jobs()]
    return {"running": scheduler.running, "jobs": jobs}


@app.get("/alerts/history")
def alert_history():
    import sqlite3
    from backend.database import get_db_path
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM alert_history ORDER BY sent_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return {"alerts": [dict(r) for r in rows]}