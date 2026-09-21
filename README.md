# Settlement Intelligence Agent

Agent monitoring settlement marketplace (Tokopedia/Shopee/TikTok Shop) yang berjalan otomatis setiap hari, menghitung proyeksi kas, dan mengirim alert actionable ke Telegram.

## Stack
- **Orchestration:** Langflow (self-hosted via Docker)
- **LLM:** `groq/compound-mini` (validated, skor 100% spike test)
- **Kalkulasi:** Python 3.11+ custom components
- **Scheduler:** FastAPI + APScheduler
- **Delivery:** python-telegram-bot
- **DB:** SQLite (MVP)

## Quick Start

### 1. Clone & Setup
```bash
git clone https://github.com/Steven-Tampubolon/settlement-intelligence-agent.git
cd settlement-intelligence-agent
cp .env.example .env
# Edit .env dengan API keys Anda
```

### 2. Jalankan Langflow via Docker
```bash
docker compose up -d
# Langflow tersedia di http://localhost:7860
```

### 3. Install dependencies backend
```bash
cd backend
pip install -r requirements.txt
```

### 4. Jalankan backend
```bash
uvicorn main:app --reload --port 8000
```

### 5. Test komponen standalone
```bash
cd langflow/components
python -m pytest ../../tests/ -v
```

## Struktur Direktori
```
settlement-intelligence-agent/
├── backend/ # FastAPI + APScheduler
├── langflow/
│ ├── components/ # Python custom components
│ ├── flows/ # Langflow flow JSON (export dari UI)
│ ├── mock_data/ # 5 skenario test
│ └── prompts/ # System prompt LLM
├── tests/ # Unit tests
├── docs/ # Dokumen arsitektur
├── docker-compose.yml
└── .env.example
```


## Environment Variables
Lihat `.env.example` untuk daftar lengkap.