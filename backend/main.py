# backend/main.py
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from backend.config import validate_config
from backend.database import init_db, seed_demo_store
from backend.scheduler.daily_monitor import run_daily_monitoring

scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    validate_config()
    init_db()
    seed_demo_store()

    # Jadwal harian jam 06:00 WIB
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
    scheduler.shutdown()


app = FastAPI(
    title="Settlement Intelligence Agent",
    description="API untuk monitoring dan trigger agent settlement marketplace",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Endpoints ──────────────────────────────────────────────────────────

class TriggerRequest(BaseModel):
    store_id: str = "toko_andi_001"
    scenario: str = "S1_AMAN"


@app.get("/health")
def health():
    return {"status": "ok", "service": "settlement-intelligence-agent"}


@app.post("/trigger")
def trigger_now(req: TriggerRequest):
    """
    Trigger monitoring manual — berguna untuk demo dan testing.
    """
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
        "message": "Monitoring berjalan di background. Cek Telegram Anda.",
    }


@app.post("/trigger/all-scenarios")
def trigger_all_scenarios():
    """
    Jalankan semua 5 skenario secara berurutan — untuk demo hackathon.
    """
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
    jobs = [
        {
            "id": job.id,
            "next_run": str(job.next_run_time),
        }
        for job in scheduler.get_jobs()
    ]
    return {"running": scheduler.running, "jobs": jobs}