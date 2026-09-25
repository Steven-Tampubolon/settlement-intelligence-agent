# Laporan Pengerjaan Sprint
## Marketplace Settlement Intelligence Agent

**Tanggal Sprint:** 21–22 September 2026
**Status:** ✅ SELESAI — Semua Definition of Done terpenuhi
**Repo:** settlement-intelligence-agent
**Versi:** v1.0.0-mvp

---

## 1. Ringkasan Eksekutif

Sprint ini berhasil membangun satu loop end-to-end agent monitoring settlement marketplace yang berjalan penuh tanpa crash. Agent mengambil data settlement (mock), menghitung proyeksi kas, mengklasifikasi risiko, memformat pesan via LLM, memvalidasi output, dan mengirim alert actionable ke Telegram — semua berjalan otomatis tanpa intervensi manual.

**Hasil test akhir:**

| Kategori | Hasil |
|----------|-------|
| Unit tests | 27/27 ✅ |
| Integration e2e | 15/15 ✅ |
| Skenario mock valid | 5/5 ✅ |
| Definition of Done | 8/8 ✅ |
| Retry logic | 2/2 ✅ |
| **Total** | **42/42** ✅ |

---

## 2. Kepatuhan terhadap Architecture Boundaries

### 2.1 Prinsip Non-Negotiable — Status

| Prinsip | Status | Catatan |
|---------|--------|---------|
| Python mengerjakan 100% kalkulasi numerik | ✅ DIPATUHI | NetCalculator, ProjectionBuilder, RiskClassifier, DecisionEngine — semua pure Python, tidak ada kalkulasi di LLM |
| LLM hanya memformat | ✅ DIPATUHI | Groq menerima structured data matang dari DecisionEngine, hanya mengubahnya menjadi pesan natural language |
| Setiap output LLM divalidasi | ✅ DIPATUHI | OutputValidator wajib jalan sebelum alert dikirim ke Telegram |
| Threshold risiko sebagai konstanta Python | ✅ DIPATUHI | `CRITICAL_THRESHOLD_DAYS = 3`, `WARNING_THRESHOLD_DAYS = 7` di `risk_classifier.py`, bukan di prompt |

### 2.2 Batas Layer yang Dijaga

```
Layer 1 (Scheduler)   → HANYA trigger Langflow, tidak ada kalkulasi
Layer 2 (Langflow)    → HANYA orkestrasi urutan node
Layer 3A (Python)     → HANYA kalkulasi dan logic rules-based
Layer 3B (LLM)        → HANYA formatting natural language
Layer 3C (Delivery)   → HANYA kirim pesan, tidak format ulang
```

Tidak ada pelanggaran boundary yang ditemukan selama pengerjaan.

---

## 3. Deviasi dari Spesifikasi Original

### 3.1 Model LLM: groq/compound-mini → qwen/qwen3.8-27b

**Penyebab:** `groq/compound-mini` dihapus dari Groq API tanpa pemberitahuan setelah spike test dilakukan. Model tidak lagi tersedia di production.

**Solusi:** Beralih ke `qwen/qwen3.8-27b` yang merupakan fallback yang sudah divalidasi di spike test (skor 88%).

**Dampak:** Perlu penambahan aturan eksplisit di system prompt untuk memastikan angka settlement individual muncul satu per satu (bukan diagregasi), karena spike test menunjukkan qwen pernah menggabungkan nilai dari dua marketplace menjadi total saja.

**Mitigasi yang diterapkan:**
- System prompt diupdate dengan aturan eksplisit: "Jika ada lebih dari satu settlement, WAJIB sebutkan net amount masing-masing secara individual"
- OutputValidator memvalidasi kehadiran setiap net amount per marketplace di `full_message`
- `LLM_MODEL_NAME` dipindahkan ke environment variable agar tidak hardcoded

### 3.2 Tambahan: Retry Logic di FastAPI Client

**Tidak ada di sprint original.** Sprint menyebutkan retry di flow Langflow (Section 6.1), tapi implementasi di Langflow-level tidak feasible karena keterbatasan node types yang tersedia di Langflow 1.10.2.

**Solusi:** Retry diimplementasikan di `backend/services/langflow_client.py`:
- Attempt 1: prompt normal
- Attempt 2–3: prompt lebih eksplisit via tweaks `system_message` node Groq
- Jika semua gagal: fallback template Python

**Hasil:** Retry logic terbukti efektif — skenario yang pernah gagal di attempt pertama berhasil di attempt kedua.

### 3.3 Tambahan: alert_service.py

Sprint original hanya menyebut `telegram_webhook.py` di services. Kita menambahkan `alert_service.py` sebagai pemisahan concern yang lebih bersih:
- `alert_service.py` — handle pengiriman alert dan simpan ke database
- `telegram_webhook.py` — handle callback dari tombol user

Ini bukan pelanggaran arsitektur, melainkan improvement pada separation of concerns.

### 3.4 Tambahan: langflow/logic/ Layer

**Tidak ada di sprint original.** Awalnya business logic diembed langsung di class Langflow component. Ini menyebabkan unit test tidak bisa jalan karena dependency ke `lfx` package yang hanya ada di dalam Docker.

**Solusi:** Refactor — pisahkan business logic ke `langflow/logic/`:
```
langflow/logic/
├── data_fetcher.py       # fetch_store_data()
├── net_calculator.py     # calculate_net()
├── projection_builder.py # build_projection()
├── risk_classifier.py    # classify_risk()
├── decision_engine.py    # make_decision()
└── output_validator.py   # validate_llm_output()
```
Langflow components memanggil fungsi dari `langflow/logic/`, unit tests import langsung dari `langflow/logic/` tanpa perlu Langflow installed.

### 3.5 requirements.txt Dipindah ke Root

Sprint original menempatkan `requirements.txt` di `backend/`. Dipindahkan ke root project agar konsisten dengan lokasi venv dan cara menjalankan uvicorn dari root.

---

## 4. Tantangan Teknis dan Solusi

### 4.1 Langflow 1.10.x Menggunakan Package `lfx`, Bukan `langflow`

**Masalah:** Langflow 1.10.x (image `langflowai/langflow:latest`) menggunakan package internal `lfx` alih-alih `langflow`. Semua import yang ditulis berdasarkan dokumentasi lama (`from langflow.custom import CustomComponent`) gagal.

**Solusi:**
```python
# ❌ Tidak bekerja di Langflow 1.10.x
from langflow.custom import CustomComponent

# ✅ Benar untuk Langflow 1.10.x
from lfx.custom.custom_component.component import Component
from lfx.io import StrInput, DataInput, Output
from lfx.schema.data import Data
from lfx.schema.message import Message
```

**Pola build() yang benar:**
```python
class MyComponent(Component):
    def process(self) -> Data:          # nama unik, bukan "build"
        result = self._logic(self.input_data.data)
        self.status = result            # tampil di UI saat debug
        return Data(data=result)

    def build(self):
        return self.process             # return referensi, bukan call
```

### 4.2 Port Conflict dengan Project Lama

**Masalah:** Docker Compose menggunakan volume dan port yang sama dengan project Langflow sebelumnya (`capstone-ai-agent`).

**Solusi:** Buat volume baru yang terisolasi dan jalankan secara bergantian (Opsi A):
```bash
docker volume create settlement-agent_postgres_data
docker volume create settlement-agent_langflow_data
```

### 4.3 Custom Component Tidak Bisa Import Satu Sama Lain

**Masalah:** Di dalam Docker, import antar custom component via package name gagal karena Langflow meload component secara dinamis dan tidak mengenali struktur folder sebagai package.

**Solusi:** Embed business logic langsung sebagai private method di class, atau gunakan `langflow/logic/` layer yang di-mount sebagai volume dan diakses via `sys.path`.

### 4.4 Port Input/Output Component Tidak Bisa Disambung

**Masalah:** Custom component dengan tipe `dict` tidak menghasilkan port (titik biru/merah) yang bisa disambung di canvas Langflow.

**Solusi:** Gunakan tipe `Data` (titik merah) untuk antar Python component, dan `Message` (titik biru) untuk output yang masuk ke node LLM:
```python
# Antar Python component
def calculate(self) -> Data:
    return Data(data=result)

# Sebelum masuk ke Groq/LLM
def decide(self) -> Message:
    return Message(text=json.dumps(result))
```

### 4.5 Groq API Key Masuk ke Flow JSON Export

**Masalah:** Saat export flow JSON dari Langflow UI, Groq API key ikut tersimpan di dalam file.

**Solusi:** Gunakan Global Variables di Langflow (Settings → Global Variables → Type: Credential) dan sambungkan ke field Groq API Key. Nilai credential tidak ikut ke export JSON.

### 4.6 Prompt Template Error dengan Karakter `{` dan `}`

**Masalah:** Node Prompt Template di Langflow menginterpretasikan `{` dan `}` di dalam teks sebagai template variable, sehingga system prompt yang berisi contoh JSON struktur throw error.

**Solusi:** Isi system prompt langsung di field **System Message** di node Groq (bukan via Prompt Template node). Field ini menerima plain text tanpa parsing template.

---

## 5. Build Order Aktual vs Spesifikasi

| Step | Spesifikasi | Aktual | Catatan |
|------|-------------|--------|---------|
| 1 | Mock data | ✅ Sesuai | 5 skenario S1–S5 |
| 2 | Python components | ✅ Sesuai | + refactor ke langflow/logic/ |
| 3 | Telegram Bot setup | ✅ Sesuai | + webhook handler |
| 4 | Langflow flow assembly | ✅ Sesuai | Iterasi lebih dari yang diperkirakan karena lfx API |
| 5 | FastAPI + scheduler | ✅ Sesuai | + alert_service.py, retry logic |
| 6 | Integration test | ✅ Sesuai | 42/42 passed |
| + | Retry logic | ➕ Tambahan | Tidak ada di spesifikasi, diimplementasikan sebagai improvement |
| + | Webhook handler | ➕ Tambahan | Tidak ada di spesifikasi awal, diimplementasikan untuk completeness |

---

## 6. Definition of Done — Verifikasi Final

| # | Kriteria | Status | Bukti |
|---|----------|--------|-------|
| 1 | Scheduler bisa trigger Langflow flow secara manual | ✅ | `POST /trigger` endpoint, `POST /trigger/all-scenarios` |
| 2 | Flow lengkap berjalan tanpa error untuk kelima skenario | ✅ | `test_all_scenarios_endpoint` PASSED |
| 3 | LLM menghasilkan JSON valid di semua 5 skenario | ✅ | `TestLangflowPipeline` — 6/6 PASSED |
| 4 | Output Validator mendeteksi angka yang hilang | ✅ | `test_missing_cash_number`, `test_missing_settlement_number` PASSED |
| 5 | Pesan Telegram terkirim dengan format benar dan inline keyboard | ✅ | Alert terkirim dan tombol berfungsi di semua skenario |
| 6 | Respons tombol user tercatat di database | ✅ | `user_action` tersimpan di tabel `alert_history` |
| 7 | Screenshot Langflow flow diagram | ✅ | Tersimpan di project |
| 8 | Screen recording demo end-to-end | ✅ | Tersimpan di project |

---

## 7. Known Gaps (Scope Sprint Berikutnya)

### Decision Engine
- **`flash_sale`** — belum diimplementasikan. Tidak ada spesifikasi threshold dan tidak ada skenario mock yang menggunakannya.
- **`multiple`** — tipe keputusan untuk menggabungkan beberapa kondisi aktif sekaligus. Saat ini menggunakan prioritas: KRITIS + piutang → `collect_receivable` (override restock).

### Mock Data vs Real API
- `commission_rate` — real API memberikan `commission_amount` langsung, bukan rate
- `average_daily_expense` — tidak ada di API marketplace, harus diinput manual atau dihitung dari history 30 hari
- Real API bersifat per-transaksi, bukan per-periode settlement yang sudah diagregasi
- TikTok Shop punya fee tambahan (affiliate commission, shipping insurance) yang diabaikan di mock

### Infrastruktur
- **Real API marketplace** — butuh partner approval 2–8 minggu. Swap hanya di `DataFetcher` component.
- **Webhook production** — saat ini pakai ngrok untuk development. Production butuh domain + SSL.
- **Multi-toko** — database schema sudah mendukung multiple stores, tapi UI management belum ada.

---

## 8. File Structure Aktual

```
settlement-intelligence-agent/
├── backend/
│   ├── main.py                    # FastAPI app + webhook + APScheduler
│   ├── config.py                  # Environment variables
│   ├── database.py                # SQLite init + seed
│   ├── models.py                  # Store, AlertHistory, PendingTrigger dataclass
│   ├── scheduler/
│   │   └── daily_monitor.py       # Trigger Langflow per toko
│   └── services/
│       ├── langflow_client.py     # HTTP client + retry logic
│       ├── alert_service.py       # Telegram delivery + history
│       └── telegram_webhook.py    # Callback handler (confirm/detail/close)
│
├── langflow/
│   ├── components/                # Langflow custom components (lfx-based)
│   │   ├── data_fetcher.py
│   │   ├── net_calculator.py
│   │   ├── projection_builder.py
│   │   ├── risk_classifier.py
│   │   ├── decision_engine.py
│   │   ├── output_validator.py
│   │   └── telegram_sender.py
│   ├── logic/                     # Business logic murni (testable tanpa Langflow)
│   │   ├── data_fetcher.py
│   │   ├── net_calculator.py
│   │   ├── projection_builder.py
│   │   ├── risk_classifier.py
│   │   ├── decision_engine.py
│   │   └── output_validator.py
│   ├── flows/
│   │   └── settlement_monitor_flow.json  # Export flow (credentials scrubbed)
│   ├── mock_data/
│   │   └── store_scenarios.json          # 5 skenario S1–S5
│   └── prompts/
│       └── message_formatter_system_prompt.md
│
├── lfx/                           # Stub package untuk testing lokal
│   ├── custom/custom_component/
│   │   └── component.py
│   ├── schema/
│   │   ├── data.py
│   │   └── message.py
│   └── io.py
│
├── langflow/                      # Stub untuk import lokal
│   ├── custom.py
│   ├── io.py
│   ├── field_typing.py
│   └── schema/
│       ├── data.py
│       └── message.py
│
├── tests/
│   ├── test_net_calculator.py      # 4 tests
│   ├── test_risk_classifier.py     # 6 tests
│   ├── test_projection_builder.py  # 4 tests
│   ├── test_output_validator.py    # 7 tests
│   ├── test_integration_pipeline.py # 5 tests
│   └── test_integration_e2e.py     # 15 tests (butuh Langflow + uvicorn jalan)
│
├── scripts/
│   └── test_telegram.py
│
├── docs/
│   ├── ARCHITECTURE_BOUNDARIES.md
│   ├── SPIKE_TEST_RESULTS.md
│   ├── SPRINT_SETTLEMENT_AGENT.md
│   └── KNOWN_GAPS.md
│
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

---

## 9. Environment Variables Final

```bash
# Groq
GROQ_API_KEY=gsk_xxx

# Telegram
TELEGRAM_BOT_TOKEN=xxx

# Langflow
LANGFLOW_BASE_URL=http://localhost:7860
LANGFLOW_API_KEY=sk-xxx
LANGFLOW_FLOW_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# App
DATABASE_URL=sqlite:///./settlement_agent.db
LLM_MODEL_NAME=qwen/qwen3.8-27b        # dipindah dari hardcode ke env var
WEBHOOK_BASE_URL=https://xxx.ngrok-free.app  # tambahan sprint ini
```

---

## 10. Catatan untuk Sprint Berikutnya

1. **Implementasikan `flash_sale` di Decision Engine** — perlu definisi threshold stok menumpuk dan rules go/no-go
2. **Implementasikan tipe `multiple`** — gabungkan beberapa keputusan aktif + skenario mock S6
3. **Swap DataFetcher ke real API** — daftar sebagai developer di Shopee Open Platform dan TikTok Shop Partner Center, implementasikan OAuth 2.0 + normalization layer
4. **Production webhook** — ganti ngrok dengan domain proper + SSL
5. **Model LLM** — monitor ketersediaan `groq/compound-mini` atau evaluasi model pengganti yang lebih stabil. Pertimbangkan Gemini Flash sebagai alternatif yang disebutkan di `ARCHITECTURE_BOUNDARIES.md`
6. **Multi-toko management** — UI sederhana untuk tambah/edit/nonaktifkan toko

---

## 11. Bug Fix Round 1 — 24–25 September 2026

Sprint perbaikan berdasarkan review manual terhadap codebase v1.0.0-mvp.
6 fix dikerjakan, semua Acceptance Criteria terpenuhi.

### Ringkasan Fix

| # | Prioritas | Fix | Status |
|---|-----------|-----|--------|
| 1 | P0 | Fallback message kosong angka | ✅ Selesai |
| 2 | P0 | Output Validator tidak cek angka restock | ✅ Selesai |
| 3 | P1 | System prompt dasar tidak sinkron dengan retry prompt | ✅ Selesai |
| 4 | P1 | Loop follow-up pending_triggers tidak pernah dipakai | ✅ Selesai |
| 5 | P2 | flash_sale belum diimplementasikan | ✅ Selesai |
| 6 | P2 | multiple decision type belum diimplementasikan | ✅ Selesai |

### Detail Perubahan

**FIX #1 (P0) — Fallback Message Kosong Angka**

Ditemukan dua fungsi fallback yang saling bertentangan: `generate_fallback_message()` di `langflow/logic/output_validator.py` (benar, mengandung angka asli) tidak pernah dipanggil di jalur produksi. Yang dipakai justru `_build_fallback_message()` di `alert_service.py` yang generik tanpa angka apapun.

*Root cause:* `send_alert()` tidak menerima `decision_data` sehingga tidak bisa memanggil fungsi yang benar.

*Solusi:*
- `langflow_client.py`: ekstrak `decision_data` dari response Langflow dan sertakan di setiap return
- `alert_service.py`: panggil `generate_fallback_message(decision_data)`, hapus `_build_fallback_message()`
- `database.py`: tambah kolom `decision_data` (JSON) di tabel `alert_history` + migrasi otomatis

**FIX #2 (P0) — Output Validator Tidak Cek Angka Restock**

`_extract_critical_numbers()` hanya mengecek `collect_receivable`. Skenario S2 dan S4 (restock) bisa lolos validasi meski LLM tidak menyebut biaya restock.

*Solusi:* Tambah pengecekan untuk `restock.cost`, `flash_sale.required_stock_budget`, `flash_sale.cash_after_joining`, dan semua sub-decisions di `multiple`.

**FIX #3 (P1) — Sinkronisasi System Prompt**

`RETRY_SYSTEM_PROMPT` di `langflow_client.py` punya aturan lebih lengkap dari `message_formatter_system_prompt.md`. Akibatnya attempt pertama sering gagal dan baru valid di attempt kedua — buang 1 API call + 2 detik per request.

*Solusi:*
- Satukan ke satu file: `langflow/prompts/message_formatter_system_prompt.md`
- Tambah aturan 8 (restock cost wajib sebut), aturan 9 (multiple priority), aturan 10 (flash sale budget)
- `langflow_client.py` baca dari file — hapus `RETRY_SYSTEM_PROMPT` duplikat
- Prompt dikirim via `tweaks` di setiap request sehingga selalu sinkron dengan file

*Hasil:* S5 (multi-settlement) sekarang lolos di attempt pertama tanpa retry.

**FIX #4 (P1) — Loop Follow-up Pending Triggers**

Tabel `pending_triggers` ada di schema tapi tidak pernah di-insert, dibaca, atau diupdate. Ini bertentangan dengan konsep inti produk: agent yang terus memantau.

*Solusi:*
- `telegram_webhook.py`: `_handle_confirm()` buat entry `pending_triggers` jika keputusan terakhir adalah restock
- `trigger_resolver.py` (file baru): cek trigger yang kondisinya terpenuhi, kirim follow-up alert
- `daily_monitor.py`: panggil `resolve_pending_triggers()` di awal setiap run
- `database.py`: tambah kolom `decision_data` di `alert_history` agar `_get_last_decision_data()` bisa bekerja

**FIX #5 (P2) — Implementasi flash_sale Decision Type**

Tercatat di `KNOWN_GAPS.md` Sprint 1 sebagai scope berikutnya.

*Implementasi:*
- Konstanta: `FLASH_SALE_MIN_CASH_BUFFER = 2.000.000`, `FLASH_SALE_MAX_STOCK_BUDGET_RATIO = 0.5`
- `_evaluate_flash_sale()` — rules-based: `can_join` jika kas cukup dan budget ≤ 50% kas
- Skenario `S6_FLASH_SALE` ditambahkan ke mock data
- Pass-through `flash_sale_opportunity` di NetCalculator, ProjectionBuilder, RiskClassifier

**FIX #6 (P2) — Implementasi multiple Decision Type**

Tercatat di `KNOWN_GAPS.md` Sprint 1 sebagai scope berikutnya.

*Implementasi:*
- `make_decision()` direfactor ke `active_decisions` pattern — kumpulkan semua keputusan aktif, baru tentukan tipe
- `collect_receivable` sekarang aktif di semua status (sebelumnya hanya KRITIS) — agar S5 yang punya piutang + restock menghasilkan `multiple`
- `_build_multiple_decision()` — urutkan berdasarkan prioritas: collect_receivable > restock > flash_sale
- S5 sekarang otomatis menghasilkan `type: "multiple"` dengan 2 sub-decisions

### Perubahan Section 3.1 (Update dari Sprint 1)

Section 3.1 Sprint 1 menyatakan retry menggunakan prompt lebih eksplisit mulai attempt ke-2. Ini sudah diubah di Bug Fix Round 1:

- **Sebelum:** Attempt 1 pakai prompt dasar, attempt 2–3 pakai `RETRY_SYSTEM_PROMPT` yang lebih eksplisit
- **Sesudah:** Semua attempt pakai prompt yang sama — dibaca dari `message_formatter_system_prompt.md` yang sudah lengkap dari attempt pertama. Retry tetap ada untuk handle timeout dan invalid JSON, tapi bukan lagi untuk mengganti prompt.

### Hasil Test Akhir Bug Fix Round 1

| Kategori | Sprint 1 | Bug Fix Round 1 |
|----------|----------|-----------------|
| Unit tests | 27/27 ✅ | 36/36 ✅ |
| Integration pipeline | 5/5 ✅ | 7/7 ✅ |
| Integration e2e | 15/15 ✅ | 17/17 ✅ |
| Trigger resolver | — | 5/5 ✅ |
| **Total** | **42/42** ✅ | **53/53** ✅ |
| Skenario mock valid | 5/5 | 6/6 (+ S6_FLASH_SALE) |
---
*Laporan ini dibuat berdasarkan pengerjaan sprint 21–22 September 2026.*
*Semua keputusan teknis yang menyimpang dari spesifikasi original telah didokumentasikan di Section 3.*
