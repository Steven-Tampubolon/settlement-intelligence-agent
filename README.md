# Settlement Intelligence Agent

Agent monitoring settlement marketplace (Tokopedia/Shopee/TikTok Shop) yang berjalan
otomatis setiap hari, menghitung proyeksi kas, mengklasifikasi risiko, dan mengirim
alert actionable ke Telegram.

## Skenario yang Didukung

| Skenario | Status | Keputusan |
|----------|--------|-----------|
| S1 — Normal | ✅ AMAN | Pantau — settlement masuk sesuai jadwal |
| S2 — Perlu Restock | ✅ AMAN | Restock mie instan setelah settlement cair |
| S3 — Kas Kritis | 🔴 KRITIS | Tagih Toko Makmur hari ini, kas Rp 850.000 |
| S4 — Restock Aman | ✅ AMAN | Restock sabun setelah Shopee cair |
| S5 — Multi-masalah | 🟡 WASPADA | Tagih piutang + restock setelah settlement |
| S6 — Peluang Flash Sale | ✅ AMAN | IKUT flash sale Shopee — kas aman setelah beli stok |


## Arsitektur

```
Scheduler (06:00 WIB)
→ Langflow Orchestrator
→ DataFetcher → NetCalculator → ProjectionBuilder
→ RiskClassifier → DecisionEngine
→ Groq LLM (qwen/qwen3.8-27b) → OutputValidator
→ FastAPI Backend
→ Telegram Alert + Inline Keyboard
→ Webhook Handler (confirm / detail / close)
→ Trigger Resolver (follow-up otomatis saat settlement cair)
```

## Stack

| Layer | Teknologi |
|-------|-----------|
| Orchestration | Langflow 1.10.x (self-hosted Docker) |
| LLM | `qwen/qwen3.8-27b` via Groq API |
| Kalkulasi | Python 3.12 custom components |
| Scheduler | FastAPI + APScheduler |
| Delivery | python-telegram-bot |
| Database | SQLite |
| Tunnel (dev) | ngrok |

## Struktur Direktori
```
settlement-intelligence-agent/
├── backend/
│ ├── main.py # FastAPI app + webhook + APScheduler
│ ├── config.py # Environment variables
│ ├── database.py # SQLite init + queries + migrasi
│ ├── models.py # Store, AlertHistory, PendingTrigger dataclass
│ ├── scheduler/
│ │ ├── daily_monitor.py # Trigger Langflow per toko
│ │ └── trigger_resolver.py # Cek dan resolve pending_triggers
│ └── services/
│ ├── langflow_client.py # Langflow REST client + retry logic
│ ├── alert_service.py # Telegram delivery + history
│ └── telegram_webhook.py # Callback handler (confirm/detail/close)
├── langflow/
│ ├── components/ # Langflow custom components (lfx-based)
│ │ ├── data_fetcher.py
│ │ ├── net_calculator.py
│ │ ├── projection_builder.py
│ │ ├── risk_classifier.py
│ │ ├── decision_engine.py
│ │ └── output_validator.py
│ ├── logic/ # Business logic murni (testable tanpa Langflow)
│ │ ├── data_fetcher.py
│ │ ├── net_calculator.py
│ │ ├── projection_builder.py
│ │ ├── risk_classifier.py
│ │ ├── decision_engine.py
│ │ └── output_validator.py
│ ├── flows/
│ │ └── settlement_monitor_flow.json # Export flow (credentials scrubbed)
│ ├── mock_data/
│ │ └── store_scenarios.json # 6 skenario S1–S6
│ └── prompts/
│ └── message_formatter_system_prompt.md # Satu sumber system prompt
├── tests/
│ ├── test_net_calculator.py # 4 tests
│ ├── test_risk_classifier.py # 6 tests
│ ├── test_projection_builder.py # 4 tests
│ ├── test_output_validator.py # 10 tests
│ ├── test_integration_pipeline.py # 7 tests
│ ├── test_integration_e2e.py # 17 tests
│ └── test_trigger_resolver.py # 5 tests
├── scripts/
│ └── test_telegram.py
├── docs/
│ ├── ARCHITECTURE_BOUNDARIES.md
│ ├── SPIKE_TEST_RESULTS.md
│ ├── SPRINT_SETTLEMENT_AGENT.md
│ ├── SPRINT_BUGFIX_ROUND1.md
│ ├── SPRINT_REPORT.md
│ └── KNOWN_GAPS.md
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Quick Start

### 1. Clone & Setup

```bash
git clone https://github.com/Steven-Tampubolon/settlement-intelligence-agent.git
cd settlement-intelligence-agent
cp .env.example .env
# Edit .env dengan API keys Anda
pip install -r requirements.txt
```

### 2. Buat Docker volumes

```bash
docker volume create settlement-agent_postgres_data
docker volume create settlement-agent_langflow_data
```

### 3. Jalankan Langflow

```bash
docker compose up -d
```

Buka `http://localhost:7860` — import flow dari `langflow/flows/settlement_monitor_flow.json`.

### 4. Setup Langflow

Di Langflow UI:
1. Import flow: klik **Import** → pilih `langflow/flows/settlement_monitor_flow.json`
2. Buat Global Variable: **Settings → Global Variables → Add New**
   - Name: `GROQ_API_KEY`, Type: `Credential`, Value: Groq API key Anda
3. Di node Groq, sambungkan field **Groq API Key** ke global variable `GROQ_API_KEY`
4. Salin Flow ID dari URL browser → masukkan ke `.env` sebagai `LANGFLOW_FLOW_ID`
5. Buat Langflow API Key: **Settings → Langflow API → Add New** → masukkan ke `.env`

### 5. Jalankan Backend

```bash
uvicorn backend.main:app --reload --port 8000
```

### 6. Setup Webhook (Development)

```bash
# Terminal terpisah
ngrok http 8000
# Copy URL https → masukkan ke .env sebagai WEBHOOK_BASE_URL
# Restart uvicorn
```

### 7. Test

```bash
# Unit tests (tanpa Langflow/uvicorn)
pytest tests/ -v --ignore=tests/test_integration_e2e.py

# Integration test e2e (butuh Langflow + uvicorn + ngrok jalan)
pytest tests/test_integration_e2e.py -v

# Test semua skenario via API
curl -X POST http://localhost:8000/trigger/all-scenarios
```

## Environment Variables

Salin `.env.example` ke `.env` dan isi semua nilai:

```bash
# Groq
GROQ_API_KEY=gsk_xxx

# Telegram
TELEGRAM_BOT_TOKEN=xxx:xxx

# Langflow
LANGFLOW_BASE_URL=http://localhost:7860
LANGFLOW_API_KEY=sk-xxx
LANGFLOW_FLOW_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# App
DATABASE_URL=sqlite:///./settlement_agent.db
LLM_MODEL_NAME=qwen/qwen3.8-27b
WEBHOOK_BASE_URL=https://xxx.ngrok-free.dev
```

## API Endpoints

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/health` | Health check |
| POST | `/trigger` | Trigger monitoring manual |
| POST | `/trigger/scenario/{scenario}` | Trigger satu skenario (S1–S6) |
| POST | `/trigger/all-scenarios` | Trigger semua 6 skenario |
| GET | `/scheduler/status` | Status scheduler |
| GET | `/alerts/history` | History alert terkirim |
| POST | `/webhook/telegram` | Webhook callback Telegram |

## Test Results
```
Unit tests: 36/36 passed
Integration pipeline: 7/7
Integration e2e: 17/17 passed
Trigger resolver: 5/5
**Total**: **53/53**
Skenario validated: 6/6 valid=true, missing_numbers=[] (+ S6_FLASH_SALE)
```


## Catatan Arsitektur

- **LLM hanya untuk formatting** — kalkulasi dan keputusan dilakukan di Python
- **Validasi berlapis** — OutputValidator memastikan angka kritis tidak hilang dari pesan
- **Fallback dengan angka asli** — jika LLM gagal 3x, fallback template Python tetap menyertakan angka kas dan settlement asli
- **Satu sumber system prompt** — `langflow/prompts/message_formatter_system_prompt.md` dipakai di semua attempt via tweaks API
- **Swap ke real API** — ganti hanya `DataFetcher` component, semua layer di atas tidak berubah
- **Threshold risiko** — konstanta di Python (`CRITICAL=3 hari`, `WARNING=7 hari`), bukan di prompt
- **Follow-up otomatis** — `trigger_resolver.py` cek `pending_triggers` setiap hari dan kirim follow-up saat kondisi terpenuhi