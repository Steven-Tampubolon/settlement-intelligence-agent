# Architecture Boundaries
## Marketplace Settlement Intelligence Agent

**Versi:** 1.1.0
**Status:** Validated — Build Approved
**Aturan utama:** Setiap komponen hanya boleh mengerjakan apa yang ada di kolom "BOLEH". Jika sesuatu masuk ke kolom "TIDAK BOLEH", arsitektur salah.

---

## Status Validasi Spike Test

Spike test dijalankan pada 3 model Groq yang tersedia di akun (lihat `SPIKE_TEST_RESULTS.md` untuk detail lengkap). Hasil ringkas:

| Model | Skor | Keputusan |
|---|---|---|
| `groq/compound-mini` | 25/25 (100%) | ✅ **PRIMARY** — angka terjaga di semua 5 skenario |
| `qwen/qwen3.8-27b` | 22/25 (88%) | ⚠️ **FALLBACK** — pernah agregasi angka individual (lihat catatan) |
| `openai/gpt-oss-20b` | 19/25 (76%) | ❌ **EXCLUDED** — JSON terpotong (truncation) di skenario S1 |

**Keputusan final: `groq/compound-mini` sebagai satu-satunya model untuk MVP.** Tidak perlu fallback logic yang rumit — skor 100% dengan angka terjaga sempurna di semua skenario termasuk yang paling kompleks (multi-settlement, multi-masalah).

Jika di kemudian hari rate limit `groq/compound-mini` (250 req/day) terlampaui, gunakan `qwen/qwen3.8-27b` sebagai fallback — TAPI wajib tambahkan validasi ekstra: pastikan setiap angka settlement per marketplace muncul individual di output, bukan hanya dijumlahkan.

---

## Gambaran Besar

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: Scheduler                                         │
│  FastAPI + APScheduler                                      │
│  "Kapan agent jalan"                                        │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP call ke Langflow API
┌────────────────────────▼────────────────────────────────────┐
│  LAYER 2: Orchestrator                                      │
│  Langflow                                                   │
│  "Urutan langkah agent"                                     │
└──────┬─────────────────┬──────────────────┬─────────────────┘
       │                 │                  │
┌──────▼──────┐  ┌───────▼───────┐  ┌──────▼──────────────┐
│  LAYER 3A   │  │   LAYER 3B    │  │     LAYER 3C        │
│  Python     │  │     LLM       │  │   Delivery          │
│  Kalkulasi  │  │  Groq /       │  │   Telegram Bot      │
│  & Logika   │  │  Gemini Flash │  │                     │
└─────────────┘  └───────────────┘  └─────────────────────┘
       │                 │
┌──────▼─────────────────▼──────────────────────────────────┐
│  DATA: Mock Marketplace Data (MVP)                         │
│  Struktur identik dengan Tokopedia / Shopee / TikTok API   │
└────────────────────────────────────────────────────────────┘
```

---

## Layer 1 — Scheduler
**Teknologi:** FastAPI + APScheduler
**Tanggung jawab:** Satu hal saja — memutuskan kapan agent dijalankan.

### BOLEH:
- Trigger Langflow API endpoint setiap hari pada waktu yang ditentukan (default: 06:00 WIB)
- Menyimpan daftar toko yang harus dimonitor (store_id, credentials)
- Retry jika Langflow tidak merespons
- Log waktu eksekusi terakhir

### TIDAK BOLEH:
- Kalkulasi apapun
- Memanggil LLM langsung
- Mengirim alert ke Telegram
- Mengandung business logic

### Contoh kode:
```python
# main.py
scheduler = APScheduler()

@scheduler.scheduled_job('cron', hour=6, minute=0)
def run_daily_monitoring():
    stores = db.get_all_active_stores()
    for store in stores:
        requests.post(
            f"{LANGFLOW_URL}/api/v1/run/{FLOW_ID}",
            json={"store_id": store.id}
        )
```

---

## Layer 2 — Orchestrator
**Teknologi:** Langflow
**Tanggung jawab:** Menentukan urutan langkah — siapa memanggil siapa dan kapan.

### BOLEH:
- Mendefinisikan urutan eksekusi: fetch → hitung → klasifikasi → format → kirim
- Meneruskan output satu komponen ke komponen berikutnya
- Routing kondisional: jika status KRITIS → flow berbeda dari AMAN
- Memanggil Python custom components
- Memanggil LLM dengan prompt yang sudah berisi data matang
- Memanggil Telegram sender

### TIDAK BOLEH:
- Kalkulasi numerik langsung di prompt node
- Menyimpan state permanen (gunakan database external)
- Menjadi scheduler (itu urusan Layer 1)

### Flow yang harus dibangun di Langflow:
```
[Input: store_id]
      ↓
[Node 1] Data Fetcher        → Python component
      ↓
[Node 2] Net Calculator      → Python component
      ↓
[Node 3] Projection Builder  → Python component
      ↓
[Node 4] Risk Classifier     → Python component
      ↓
[Node 5] Decision Engine     → Python component
      ↓
[Node 6] Message Formatter   → LLM (Groq / Gemini)
      ↓
[Node 7] Alert Sender        → Telegram Python component
```

---

## Layer 3A — Python (Kalkulasi & Logika)
**Teknologi:** Python custom components di dalam Langflow
**Tanggung jawab:** Semua yang melibatkan angka dan keputusan berbasis aturan.

### BOLEH:
- Mengambil data dari mock/API dan menormalisasinya ke format standar
- Kalkulasi net settlement:
  `net = gross - komisi - biaya_admin - subsidi_ongkir - retur`
- Membangun proyeksi kas harian (H+1 sampai H+14)
- Menghitung runway: `runway = saldo_kas / rata_pengeluaran_harian`
- Klasifikasi risiko berdasarkan threshold yang sudah didefinisikan
- Keputusan restock/flash sale berdasarkan rules yang deterministik
- Menyiapkan structured data object untuk dikirim ke LLM

### TIDAK BOLEH:
- Memformat pesan dalam bahasa natural (itu urusan LLM)
- Mengambil keputusan berdasarkan "feeling" atau probabilistik
- Memanggil LLM untuk menghitung angka

### Contoh komponen:
```python
# net_calculator.py
class NetCalculator(CustomComponent):
    def build(self, settlement_data: dict) -> dict:
        gross = settlement_data["gross_revenue"]
        commission = gross * settlement_data["commission_rate"]
        admin_fee = settlement_data["admin_fee"]
        shipping_subsidy = settlement_data["shipping_subsidy"]
        returns = settlement_data["returns_total"]

        net = gross - commission - admin_fee - shipping_subsidy - returns

        return {
            "gross": gross,
            "net": net,
            "total_deductions": gross - net,
            "breakdown": {
                "commission": commission,
                "admin_fee": admin_fee,
                "shipping_subsidy": shipping_subsidy,
                "returns": returns
            }
        }
```

```python
# risk_classifier.py
class RiskClassifier(CustomComponent):
    def build(self, projection: dict) -> dict:

        # Threshold yang sudah didefinisikan — BUKAN keputusan LLM
        CRITICAL_THRESHOLD_DAYS = 3
        WARNING_THRESHOLD_DAYS = 7

        min_runway = min(projection["daily_runway"])

        if min_runway <= CRITICAL_THRESHOLD_DAYS:
            status = "KRITIS"
        elif min_runway <= WARNING_THRESHOLD_DAYS:
            status = "WASPADA"
        else:
            status = "AMAN"

        return {
            "status": status,
            "min_runway_days": min_runway,
            "trigger_day": projection["trigger_date"]
        }
```

---

## Layer 3B — LLM
**Teknologi:** `groq/compound-mini` — **VALIDATED via spike test, skor 100%**. Model ini WAJIB dipakai kecuali rate limit terlampaui.
**Tanggung jawab:** Satu hal saja — mengubah structured data menjadi pesan natural language yang bisa dipahami Pak Andi.

### BOLEH:
- Menerima structured data object dari Python (angka sudah benar, keputusan sudah dibuat)
- Memformat data tersebut menjadi pesan Telegram yang ringkas dan natural
- Menyesuaikan tone: santai tapi informatif
- Menghasilkan JSON terstruktur sebagai output (bukan free text)

### TIDAK BOLEH:
- Melakukan kalkulasi apapun
- Membuat keputusan (restock ya/tidak, ikut flash sale ya/tidak)
- Mengakses data langsung tanpa melalui Python layer
- Menghasilkan angka yang tidak ada di input-nya

### Konfigurasi API call (WAJIB — sudah divalidasi spike test):
```python
response = client.chat.completions.create(
    model="groq/compound-mini",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ],
    temperature=0.1,  # Rendah = konsisten, terbukti di spike test
    max_tokens=800,
    response_format={"type": "json_object"}  # WAJIB — mencegah invalid JSON
)
```

### System Prompt (persis seperti yang divalidasi — jangan diubah tanpa re-test):
```
Kamu adalah asisten keuangan untuk pemilik toko online Indonesia.

Tugasmu SATU: ubah data JSON yang diberikan menjadi pesan Telegram yang singkat,
jelas, dan mudah dipahami pemilik toko yang sibuk.

ATURAN WAJIB:
1. JANGAN ubah angka sama sekali — tampilkan persis seperti di data
2. Format angka dengan titik sebagai pemisah ribuan (contoh: Rp 11.010.000)
3. Maksimal 8 baris pesan
4. Gunakan emoji secukupnya — jangan berlebihan
5. Selalu sertakan field "action_button" — satu aksi paling penting untuk user

Output HARUS berupa JSON valid dengan struktur ini:
{
  "status_line": "string — baris pertama, status + emoji",
  "incoming_funds": "string — ringkasan uang yang akan masuk",
  "key_decision": "string — satu keputusan paling penting",
  "full_message": "string — pesan lengkap siap kirim ke Telegram",
  "action_button": "string — teks tombol aksi (max 4 kata)"
}

Jangan tambahkan penjelasan di luar JSON.
```

### Contoh output tervalidasi (dari spike test S3 — skenario KRITIS):
```json
{
  "status_line": "⚠️ KRITIS – Kas Rp 850.000, runway 3 hari",
  "incoming_funds": "💰 Dana minggu ini: Rp 4.320.000 (TikTok Shop, 28 Sep)",
  "key_decision": "🛎️ Keputusan: Tagih Toko Makmur hari ini",
  "full_message": "⚠️ KRITIS – Kas Rp 850.000, runway 3 hari\n💰 Dana minggu ini: Rp 4.320.000 (TikTok Shop, 28 Sep)\n⏰ Piutang jatuh tempo: Toko Makmur Rp 3.500.000 (telat 8 hari)\n📌 Rekomendasi: Tagih Toko Makmur hari ini\n✅ Jika berhasil, kas aman sampai settlement TikTok",
  "action_button": "Tagih Sekarang"
}
```

### Validation setelah LLM output (WAJIB tetap diimplementasikan meski skor 100%):
```python
# Selalu validasi output LLM sebelum dikirim — pertahanan berlapis
def validate_llm_output(llm_response: str, source_data: dict) -> tuple[bool, list]:
    """
    Meski groq/compound-mini terbukti 100% akurat di spike test,
    validasi ini tetap WAJIB ada sebagai safety net untuk production.
    Rate limit atau load tinggi bisa mengubah perilaku model.
    """
    parsed = json.loads(llm_response)
    full_message = parsed.get("full_message", "")

    # Cek semua angka kritis dari source_data muncul di output
    critical_numbers = extract_critical_numbers(source_data)
    missing = [n for n in critical_numbers if str(f"{n:,}") not in full_message]

    if missing:
        return False, missing  # Trigger retry atau fallback template
    return True, []
```

### Fallback jika rate limit 250 req/day terlampaui:
Gunakan `qwen/qwen3.8-27b` — TAPI tambahkan pengecekan khusus: jika ada lebih dari 1 settlement per marketplace di input, pastikan setiap nilai individual muncul di output (bukan hanya dijumlahkan). Spike test menunjukkan model ini pernah menggabungkan Rp 6.800.000 + Rp 3.200.000 menjadi total tanpa merinci per marketplace.

---

## Layer 3C — Delivery
**Teknologi:** Telegram Bot API (python-telegram-bot)
**Tanggung jawab:** Mengirim pesan ke user dan menerima respons.

### BOLEH:
- Mengirim pesan alert ke Telegram user
- Menampilkan inline keyboard (tombol aksi: ✅ Oke / 🔄 Detail)
- Menerima respons user dan mengirimnya kembali ke Langflow untuk aksi lanjutan
- Menyimpan chat_id per toko

### TIDAK BOLEH:
- Memformat isi pesan (itu sudah selesai di LLM layer)
- Membuat keputusan berdasarkan respons user
- Menyimpan data keuangan

---

## Data Layer — Mock Marketplace Data (MVP)
**Tujuan:** Menggantikan real Tokopedia/Shopee/TikTok API untuk demo hackathon.

### Struktur data yang harus dimock:
```json
{
  "store_id": "toko_andi_001",
  "marketplace": "shopee",
  "period": "2026-09-15 to 2026-09-21",
  "settlements": [
    {
      "settlement_id": "SPJ-001",
      "gross_revenue": 12400000,
      "commission_rate": 0.05,
      "admin_fee": 150000,
      "shipping_subsidy": 280000,
      "returns_total": 340000,
      "scheduled_disbursement_date": "2026-09-24",
      "status": "pending"
    }
  ],
  "current_cash_balance": 4200000,
  "average_daily_expense": 2100000,
  "pending_restock": {
    "item": "mie instan",
    "estimated_cost": 6000000,
    "stock_depletes_on": "2026-09-26"
  }
}
```

### Cara swap ke real API nanti:
Ganti satu Python component (`DataFetcher`) saja. Semua layer di atasnya tidak perlu berubah karena format output DataFetcher sudah distandardisasi.

---

## Aturan yang Tidak Boleh Dilanggar

| # | Aturan | Alasan |
|---|--------|--------|
| 1 | LLM tidak pernah menyentuh angka mentah | Risiko kalkulasi salah merusak kepercayaan user |
| 2 | Python tidak pernah generate natural language | Itu bukan tugasnya dan hasilnya kaku |
| 3 | Langflow tidak punya hardcoded business logic | Logic di Langflow sulit di-test dan di-maintain |
| 4 | Semua threshold risiko didefinisikan sebagai konstanta di Python | Bukan di prompt, bukan di Langflow config |
| 5 | Setiap LLM output divalidasi sebelum dikirim | LLM bisa hallucinate angka meski sudah di-prompt |
| 6 | Mock data strukturnya identik dengan real API | Agar swap ke real API tidak butuh refactor besar |

---

## Checklist Sebelum Build

- [x] Spike test model LLM sudah dijalankan dan divalidasi — `groq/compound-mini` skor 100%
- [x] Prompt LLM sudah ditulis dan di-test — lihat Layer 3B di atas
- [ ] Mock data sudah dibuat dengan struktur lengkap (5 skenario di spike test bisa jadi basis)
- [ ] Semua Python components sudah di-list dan scope-nya jelas
- [ ] Telegram Bot sudah di-setup dan token tersedia
- [ ] Langflow sudah di-install dan flow kosong sudah dibuat
- [ ] FastAPI + APScheduler sudah di-setup (minimal trigger manual dulu)
- [ ] Validation layer untuk LLM output sudah diimplementasikan sesuai kode di Layer 3B

---

*Dokumen ini adalah kontrak arsitektur. Jika ada komponen yang melakukan sesuatu di luar batasnya, itu adalah bug arsitektur — bukan bug kode.*
