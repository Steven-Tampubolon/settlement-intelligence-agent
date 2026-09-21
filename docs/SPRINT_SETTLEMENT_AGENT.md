# Sprint Document — Marketplace Settlement Intelligence Agent
**Versi:** 1.0.0
**Status:** Ready to Build
**Dokumen pendamping:** `ARCHITECTURE_BOUNDARIES.md` (WAJIB dibaca lebih dulu — mendefinisikan batas tanggung jawab tiap layer)

> **Untuk AI Coding Assistant:** Dokumen ini adalah spesifikasi build. Ikuti urutan fase sesuai dependency yang tertulis. Jangan mulai fase berikutnya sebelum Definition of Done fase sebelumnya terpenuhi. Setiap keputusan arsitektur yang bertentangan dengan `ARCHITECTURE_BOUNDARIES.md` harus di-flag ke user, bukan diputuskan sendiri.

---

## 1. Konteks Produk

### 1.1 Masalah
UMKM online yang jualan di Tokopedia, Shopee, dan TikTok Shop tidak pernah tahu persis:
- Berapa uang bersih yang akan masuk, dan kapan
- Apakah aman restock sekarang atau harus tunggu settlement
- Apakah aman ikut flash sale tanpa mengorbankan kas operasional

82% UMKM Indonesia tutup bukan karena produk buruk — tapi karena kehabisan kas tanpa peringatan dini (sumber: riset internal, lihat dokumen riset UMKM).

### 1.2 Solusi
Agent yang menarik data settlement dari marketplace (mock untuk MVP), menghitung proyeksi kas bersih, mendeteksi situasi yang butuh keputusan, dan mengirim alert actionable ke Telegram — bukan sekadar laporan, tapi rekomendasi konkret yang bisa langsung dieksekusi.

### 1.3 Kenapa Ini Bukan Chatbot / Generator
Agent ini **memutuskan dan bertindak**, bukan hanya menjawab pertanyaan:
```
Monitor data → Hitung proyeksi → Deteksi masalah →
Klasifikasi urgensi → Putuskan rekomendasi → Eksekusi alert → Monitor respons
```
Tidak ada langkah yang menunggu user bertanya. Agent berjalan sendiri setiap hari.

### 1.4 Prinsip Arsitektur Non-Negotiable
Dari `ARCHITECTURE_BOUNDARIES.md` — **wajib dipatuhi, sudah divalidasi via spike test:**

1. **Python mengerjakan 100% kalkulasi numerik.** LLM tidak pernah menyentuh angka mentah.
2. **LLM hanya memformat.** Menerima data matang, output pesan natural language.
3. **Model LLM yang dipakai: `groq/compound-mini`** — tervalidasi skor 100% di 5 skenario spike test.
4. **Setiap output LLM divalidasi** sebelum dikirim — cek angka kritis tidak hilang/berubah.

---

## 2. Sprint Goal

Satu loop end-to-end yang berjalan tanpa crash:

```
Scheduler trigger → Langflow jalan → Data Fetcher (mock) →
Net Calculator → Projection Builder → Risk Classifier →
Decision Engine → Message Formatter (groq/compound-mini) →
Validation → Telegram Alert Sender → User bisa respons via tombol
```

### Non-Scope Sprint Ini
- Integrasi real Tokopedia/Shopee/TikTok API (pakai mock data)
- Multi-user / multi-toko management UI
- WhatsApp integration (pakai Telegram untuk MVP)
- Payment/subscription system
- Dashboard web (fokus ke alert Telegram dulu)

---

## 3. Tech Stack (Final — Sesuai Validasi)

```
Orchestration : Langflow (self-hosted via pip install langflow)
LLM           : groq/compound-mini (PRIMARY — tervalidasi 100%)
                qwen/qwen3.8-27b (FALLBACK — dengan validasi ekstra)
Kalkulasi     : Python 3.11+ (custom components di Langflow)
Scheduler     : FastAPI + APScheduler
Delivery      : python-telegram-bot
Storage       : SQLite (MVP) — cukup untuk data toko + history alert
```

### Environment Variables
```bash
GROQ_API_KEY=your_groq_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
LANGFLOW_BASE_URL=http://localhost:7860
LANGFLOW_API_KEY=your_langflow_api_key
DATABASE_URL=sqlite:///./settlement_agent.db
```

---

## 4. Project File Structure

```
settlement-intelligence-agent/
│
├── backend/
│   ├── main.py                       # FastAPI app + APScheduler
│   ├── config.py                     # Load env vars
│   ├── database.py                   # SQLite setup
│   ├── models.py                     # Store, AlertHistory
│   ├── scheduler/
│   │   └── daily_monitor.py          # Trigger Langflow tiap hari
│   ├── services/
│   │   ├── langflow_client.py        # HTTP client ke Langflow API
│   │   └── telegram_webhook.py       # Terima respons tombol user
│   └── requirements.txt
│
├── langflow/
│   ├── flows/
│   │   └── settlement_monitor_flow.json
│   ├── components/                   # Python custom components
│   │   ├── data_fetcher.py
│   │   ├── net_calculator.py
│   │   ├── projection_builder.py
│   │   ├── risk_classifier.py
│   │   ├── decision_engine.py
│   │   ├── output_validator.py
│   │   └── telegram_sender.py
│   ├── prompts/
│   │   └── message_formatter_system_prompt.md
│   └── mock_data/
│       └── store_scenarios.json      # 5 skenario dari spike test
│
└── docs/
    ├── ARCHITECTURE_BOUNDARIES.md    # Kontrak arsitektur (sudah ada)
    ├── SPIKE_TEST_RESULTS.md         # Hasil validasi model (sudah ada)
    └── SPRINT_MVP.md                 # Dokumen ini
```

---

## 5. Database Schema

```sql
CREATE TABLE stores (
    id TEXT PRIMARY KEY,
    owner_name TEXT NOT NULL,
    telegram_chat_id TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id TEXT REFERENCES stores(id),
    status TEXT NOT NULL,              -- AMAN | WASPADA | KRITIS
    message_sent TEXT NOT NULL,
    llm_model_used TEXT NOT NULL,      -- untuk tracking model mana yang dipakai
    validation_passed BOOLEAN NOT NULL,
    user_action TEXT,                  -- respons tombol user, nullable
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pending_triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id TEXT REFERENCES stores(id),
    trigger_type TEXT NOT NULL,        -- e.g. "restock_after_settlement"
    condition_data JSON NOT NULL,
    is_resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. Langflow Flow — Spesifikasi Lengkap

### 6.1 Flow Diagram

```
[Input: store_id]
      ↓
[Data Fetcher]          → ambil mock settlement data untuk store_id
      ↓
[Net Calculator]        → hitung net per settlement (gross - semua potongan)
      ↓
[Projection Builder]    → susun proyeksi kas H+0 sampai H+14
      ↓
[Risk Classifier]       → klasifikasi AMAN / WASPADA / KRITIS
      ↓
[Decision Engine]       → tentukan rekomendasi aksi spesifik
      ↓
[Message Formatter]     → LLM (groq/compound-mini) format ke JSON pesan
      ↓
[Output Validator]      → cek angka kritis tidak hilang
      ↓
   ┌──┴──┐
   │     │
[Valid] [Invalid]
   │     │
   │     └→ Retry dengan prompt lebih eksplisit (max 2x)
   │            │
   │            └→ Jika tetap gagal: gunakan fallback template Python
   ↓
[Telegram Sender]       → kirim ke chat_id user dengan inline keyboard
```

### 6.2 Kontrak Data Antar Komponen

**Data Fetcher → Net Calculator:**
```json
{
  "store_id": "string",
  "owner_name": "string",
  "current_cash_balance": "number",
  "average_daily_expense": "number",
  "settlements": [
    {
      "settlement_id": "string",
      "marketplace": "string",
      "gross_revenue": "number",
      "commission_rate": "number",
      "admin_fee": "number",
      "shipping_subsidy": "number",
      "returns_total": "number",
      "scheduled_disbursement_date": "string (ISO date)"
    }
  ],
  "overdue_receivables": [
    {"buyer": "string", "amount": "number", "overdue_days": "number"}
  ],
  "pending_stock_need": {
    "item": "string",
    "estimated_cost": "number",
    "stock_depletes_on": "string (ISO date)"
  }
}
```

**Net Calculator → Projection Builder:**
```json
{
  "settlements_net": [
    {
      "marketplace": "string",
      "net_amount": "number",
      "disbursement_date": "string",
      "breakdown": {
        "commission": "number",
        "admin_fee": "number",
        "shipping_subsidy": "number",
        "returns": "number"
      }
    }
  ],
  "total_net_incoming": "number"
}
```

**Projection Builder → Risk Classifier:**
```json
{
  "daily_projection": [
    {"date": "string", "projected_balance": "number"}
  ],
  "min_balance_day": "string",
  "min_balance_amount": "number",
  "runway_days": "number"
}
```

**Risk Classifier → Decision Engine:**
```json
{
  "status": "AMAN | WASPADA | KRITIS",
  "runway_days": "number",
  "trigger_reasons": ["string"]
}
```

**Decision Engine → Message Formatter (input final untuk LLM):**
```json
{
  "store_owner": "string",
  "status": "AMAN | WASPADA | KRITIS",
  "current_cash": "number",
  "runway_days": "number",
  "settlements": [...],
  "total_incoming_this_week": "number",
  "pending_decision": {
    "type": "restock | flash_sale | collect_receivable | multiple",
    "recommendation": "string",
    "...": "field lain sesuai tipe keputusan"
  }
}
```

> **Catatan:** Struktur ini PERSIS sama dengan struktur data yang dipakai di spike test (lihat 5 skenario di `langflow/mock_data/store_scenarios.json`). Konsistensi ini penting karena prompt LLM sudah divalidasi dengan struktur ini.

---

## 7. Spesifikasi Python Components

### 7.1 Data Fetcher
```python
class DataFetcher(CustomComponent):
    """
    BOLEH: Baca mock data, normalisasi struktur
    TIDAK BOLEH: Kalkulasi, keputusan bisnis
    """
    def build(self, store_id: str) -> dict:
        # MVP: baca dari mock_data/store_scenarios.json
        # Production nanti: ganti dengan real API call
        with open("mock_data/store_scenarios.json") as f:
            all_stores = json.load(f)
        return all_stores.get(store_id)
```

### 7.2 Net Calculator
```python
class NetCalculator(CustomComponent):
    """
    BOLEH: Kalkulasi net = gross - semua potongan
    TIDAK BOLEH: Apapun yang butuh natural language
    """
    def build(self, raw_data: dict) -> dict:
        settlements_net = []
        for s in raw_data["settlements"]:
            commission = s["gross_revenue"] * s["commission_rate"]
            net = (s["gross_revenue"] - commission
                   - s["admin_fee"] - s["shipping_subsidy"]
                   - s["returns_total"])
            settlements_net.append({
                "marketplace": s["marketplace"],
                "net_amount": net,
                "disbursement_date": s["scheduled_disbursement_date"],
                "breakdown": {
                    "commission": commission,
                    "admin_fee": s["admin_fee"],
                    "shipping_subsidy": s["shipping_subsidy"],
                    "returns": s["returns_total"]
                }
            })
        return {
            "settlements_net": settlements_net,
            "total_net_incoming": sum(s["net_amount"] for s in settlements_net)
        }
```

### 7.3 Projection Builder
```python
class ProjectionBuilder(CustomComponent):
    """
    BOLEH: Proyeksi kas harian 14 hari ke depan
    """
    def build(self, net_data: dict, raw_data: dict) -> dict:
        balance = raw_data["current_cash_balance"]
        daily_expense = raw_data["average_daily_expense"]
        projection = []

        for day_offset in range(15):  # H+0 sampai H+14
            date = (datetime.now() + timedelta(days=day_offset)).date()
            balance -= daily_expense

            for s in net_data["settlements_net"]:
                if s["disbursement_date"] == str(date):
                    balance += s["net_amount"]

            projection.append({"date": str(date), "projected_balance": balance})

        min_day = min(projection, key=lambda x: x["projected_balance"])
        runway = next(
            (i for i, p in enumerate(projection) if p["projected_balance"] <= 0),
            14  # jika tidak pernah minus dalam 14 hari
        )

        return {
            "daily_projection": projection,
            "min_balance_day": min_day["date"],
            "min_balance_amount": min_day["projected_balance"],
            "runway_days": runway
        }
```

### 7.4 Risk Classifier
```python
class RiskClassifier(CustomComponent):
    """
    BOLEH: Klasifikasi berdasarkan threshold TETAP (bukan LLM judgment)
    """
    # Threshold ini adalah KONSTANTA — jangan pindahkan ke prompt LLM
    CRITICAL_THRESHOLD_DAYS = 3
    WARNING_THRESHOLD_DAYS = 7

    def build(self, projection: dict) -> dict:
        runway = projection["runway_days"]

        if runway <= self.CRITICAL_THRESHOLD_DAYS:
            status = "KRITIS"
        elif runway <= self.WARNING_THRESHOLD_DAYS:
            status = "WASPADA"
        else:
            status = "AMAN"

        return {
            "status": status,
            "runway_days": runway,
            "min_balance_amount": projection["min_balance_amount"]
        }
```

### 7.5 Decision Engine
```python
class DecisionEngine(CustomComponent):
    """
    BOLEH: Rules-based decision (restock timing, flash sale go/no-go)
    TIDAK BOLEH: Probabilistic/LLM-based decision
    """
    def build(self, raw_data: dict, net_data: dict, risk: dict) -> dict:
        decision = None

        # Rule: cek kebutuhan restock
        stock_need = raw_data.get("pending_stock_need")
        if stock_need:
            depletion_date = stock_need["stock_depletes_on"]
            best_settlement = self._find_settlement_before(
                net_data["settlements_net"], depletion_date
            )
            decision = {
                "type": "restock",
                "item": stock_need["item"],
                "cost": stock_need["estimated_cost"],
                "stock_depletes": depletion_date,
                "recommendation": self._build_restock_recommendation(
                    best_settlement, stock_need
                )
            }

        # Rule: cek piutang jatuh tempo saat KRITIS
        if risk["status"] == "KRITIS" and raw_data.get("overdue_receivables"):
            decision = {
                "type": "collect_receivable",
                "receivables": raw_data["overdue_receivables"],
                "recommendation": "Tagih piutang tertua hari ini untuk dana operasional"
            }

        return {
            "store_owner": raw_data["owner_name"],
            "status": risk["status"],
            "current_cash": raw_data["current_cash_balance"],
            "runway_days": risk["runway_days"],
            "settlements": net_data["settlements_net"],
            "total_incoming_this_week": net_data["total_net_incoming"],
            "pending_decision": decision
        }

    def _find_settlement_before(self, settlements, deadline):
        # Logika: cari settlement yang masuk sebelum stok habis
        ...

    def _build_restock_recommendation(self, settlement, stock_need):
        # Logika rules-based, BUKAN LLM
        ...
```

### 7.6 Output Validator
```python
class OutputValidator(CustomComponent):
    """
    BOLEH: Validasi output LLM terhadap source data
    Berdasarkan hasil spike test — meski groq/compound-mini 100% akurat,
    validasi ini tetap WAJIB sebagai safety net.
    """
    def build(self, llm_output: str, decision_data: dict) -> dict:
        try:
            parsed = json.loads(llm_output)
        except json.JSONDecodeError:
            return {"valid": False, "reason": "invalid_json", "parsed": None}

        full_message = parsed.get("full_message", "")
        critical_numbers = self._extract_critical_numbers(decision_data)

        missing = [
            n for n in critical_numbers
            if f"{n:,}".replace(",", ".") not in full_message
        ]

        if missing:
            return {"valid": False, "reason": "missing_numbers",
                     "missing": missing, "parsed": parsed}

        return {"valid": True, "parsed": parsed}

    def _extract_critical_numbers(self, decision_data: dict) -> list:
        numbers = [decision_data["current_cash"]]
        for s in decision_data["settlements"]:
            numbers.append(s["net_amount"])
        if decision_data.get("pending_decision"):
            for key in ["cost", "amount"]:
                if key in decision_data["pending_decision"]:
                    numbers.append(decision_data["pending_decision"][key])
        return [n for n in numbers if n > 10000]
```

### 7.7 Telegram Sender
```python
class TelegramSender(CustomComponent):
    """
    BOLEH: Kirim pesan + inline keyboard, simpan history
    TIDAK BOLEH: Format ulang pesan (sudah selesai di LLM layer)
    """
    def build(self, validated_output: dict, chat_id: str, store_id: str) -> dict:
        message = validated_output["parsed"]["full_message"]
        button_text = validated_output["parsed"]["action_button"]

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✅ {button_text}", callback_data=f"confirm_{store_id}"),
            InlineKeyboardButton("🔄 Detail", callback_data=f"detail_{store_id}")
        ]])

        bot.send_message(chat_id=chat_id, text=message, reply_markup=keyboard)

        # Simpan ke alert_history
        db.save_alert_history(
            store_id=store_id,
            status=validated_output["parsed"]["status_line"],
            message_sent=message,
            llm_model_used="groq/compound-mini",
            validation_passed=True
        )

        return {"sent": True, "timestamp": datetime.now().isoformat()}
```

---

## 8. Mock Data — Gunakan 5 Skenario dari Spike Test

File `langflow/mock_data/store_scenarios.json` harus berisi 5 skenario yang PERSIS sama dengan yang sudah divalidasi di spike test (S1–S5). Ini penting karena:

1. Prompt LLM sudah terbukti bekerja dengan struktur data ini
2. Untuk demo, kita bisa tunjukkan variasi status (AMAN/WASPADA/KRITIS) dengan data yang sudah teruji

Struktur mengacu ke `SPIKE_TEST_RESULTS.md` — salin langsung `data` dari masing-masing skenario S1 sampai S5.

---

## 9. Definition of Done

Sprint dianggap selesai ketika:

1. ✅ Scheduler bisa trigger Langflow flow secara manual (belum perlu cron otomatis untuk demo)
2. ✅ Flow lengkap berjalan tanpa error untuk kelima skenario mock data
3. ✅ `groq/compound-mini` menghasilkan JSON valid di semua 5 skenario (sesuai hasil spike test)
4. ✅ Output Validator berhasil mendeteksi jika ada angka yang hilang (test dengan sengaja merusak salah satu skenario)
5. ✅ Pesan Telegram terkirim dengan format yang benar dan inline keyboard berfungsi
6. ✅ Respons tombol user tercatat di database
7. ✅ Screenshot Langflow flow diagram tersedia untuk pitching deck
8. ✅ Screen recording demo end-to-end (trigger → alert masuk Telegram → user klik tombol)

---

## 10. Build Order (Berdasarkan Dependency)

```
1. Mock data (store_scenarios.json)
   → Tidak ada dependency, mulai di sini

2. Python components (7.1 – 7.6)
   → Hanya butuh mock data, bisa ditest standalone tanpa Langflow

3. Telegram Bot setup
   → Paralel dengan langkah 2, tidak saling bergantung

4. Langflow flow assembly
   → Rangkai komponen dari langkah 2 sesuai diagram di Section 6.1

5. FastAPI + scheduler
   → Butuh Langflow API endpoint sudah bisa dipanggil

6. Integration test end-to-end
   → Jalankan kelima skenario, verifikasi Telegram alert sesuai ekspektasi
```

---

## 11. Known Risks (Ringkasan dari Architecture Boundaries)

| Risk | Mitigasi |
|---|---|
| Rate limit `groq/compound-mini` 250 req/day | Cukup untuk demo. Fallback ke `qwen/qwen3.8-27b` jika perlu, dengan validasi ekstra |
| LLM hallucinate angka | Output Validator wajib jalan sebelum kirim ke Telegram |
| Langflow tidak punya scheduler native | FastAPI + APScheduler sebagai layer terpisah |
| Real marketplace API butuh partner approval (lama) | Mock data untuk MVP, swap `DataFetcher` saja nanti |

---

*Dokumen ini adalah kontrak build. Jika AI coding assistant menemukan kondisi yang tidak tercakup di sini, tanyakan ke user sebelum membuat asumsi arsitektur baru.*
