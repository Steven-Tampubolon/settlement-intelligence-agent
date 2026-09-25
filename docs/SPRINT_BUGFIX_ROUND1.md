# Sprint Document — Bug Fix & Gap Closure
## Marketplace Settlement Intelligence Agent

**Versi:** 1.0.0
**Status:** Ready to Execute
**Dasar dokumen ini:** Hasil review manual terhadap codebase `settlement-intelligence-agent` v1.0.0-mvp, dibandingkan dengan `docs/ARCHITECTURE_BOUNDARIES.md` dan `docs/SPRINT_SETTLEMENT_AGENT.md`.

> **Untuk AI Coding Assistant:** Setiap item di bawah punya file spesifik, kode saat ini, kode yang seharusnya, dan Acceptance Criteria. Kerjakan sesuai urutan prioritas (P0 → P1 → P2). Jangan gabungkan dua fix dalam satu commit — memudahkan review. Setelah tiap fix, jalankan test yang relevan sebelum lanjut ke item berikutnya.

---

## Ringkasan Temuan

| # | Prioritas | Judul | File Terdampak |
|---|---|---|---|
| 1 | 🔴 P0 | Fallback message kosong angka | `backend/services/alert_service.py` |
| 2 | 🔴 P0 | Output Validator tidak cek angka restock | `langflow/logic/output_validator.py` |
| 3 | 🟡 P1 | System prompt dasar belum sinkron dengan retry prompt | `langflow/prompts/message_formatter_system_prompt.md`, `backend/services/langflow_client.py` |
| 4 | 🟠 P1 | Loop follow-up (`pending_triggers`) tidak pernah dipakai | `backend/services/telegram_webhook.py`, `backend/scheduler/daily_monitor.py` (baru) |
| 5 | 🟠 P2 | `flash_sale` belum diimplementasikan | `langflow/logic/decision_engine.py`, `langflow/mock_data/store_scenarios.json` |
| 6 | 🟢 P2 | `multiple` decision type belum diimplementasikan | `langflow/logic/decision_engine.py` |

P0 harus selesai sebelum submission apapun — keduanya menyentuh integritas angka yang dikirim ke user, yang merupakan prinsip non-negotiable di `ARCHITECTURE_BOUNDARIES.md`. P1 memperbaiki konsistensi dan diferensiasi produk. P2 menambah cakupan skenario.

---

## FIX #1 (P0) — Fallback Message Kosong Angka

### Masalah
Ada dua fungsi fallback yang saling bertentangan:

- `langflow/logic/output_validator.py::generate_fallback_message()` — **benar**, menyusun pesan dengan angka asli dari `decision_data`. Diuji di `tests/test_output_validator.py::test_fallback_message_structure`. **Tapi tidak pernah dipanggil di kode produksi.**
- `backend/services/alert_service.py::_build_fallback_message()` — **yang benar-benar dipakai**. Mengabaikan `decision_data` sepenuhnya, menghasilkan pesan generik tanpa satupun angka, dan mereferensikan "dashboard" yang tidak ada di MVP ini.

### Kode Saat Ini (Bermasalah)
```python
# backend/services/alert_service.py
def send_alert(store_id: str, validated_output: dict) -> dict:
    ...
    is_valid = validated_output.get("valid", False)
    parsed = validated_output.get("parsed", {})

    if not is_valid or not parsed:
        message = _build_fallback_message(validated_output)  # ← generik, tanpa angka
        button_text = "Lihat Detail"
        model_used = "fallback_template"
    ...

def _build_fallback_message(validated_output: dict) -> str:
    reason = validated_output.get("reason", "unknown")
    return (
        f"⚠️ Alert Settlement\n"
        f"Sistem mendeteksi kondisi yang perlu diperhatikan.\n"
        f"Silakan cek dashboard untuk detail lengkap.\n"
        f"<i>(Fallback — validasi gagal: {reason})</i>"
    )
```

### Root Cause
`send_alert()` hanya menerima `validated_output` (hasil dari `LangflowClient.run_flow()`), yang **tidak membawa `decision_data` asli** — hanya `{valid, parsed, reason, missing_numbers}`. Jadi `alert_service.py` tidak punya bahan untuk memanggil `generate_fallback_message(decision_data)` bahkan jika mau.

### Perbaikan yang Harus Dilakukan

**Langkah 1** — `LangflowClient.run_flow()` di `backend/services/langflow_client.py` harus meneruskan `decision_data` mentah (bukan hanya hasil validasi) di setiap return, termasuk saat fallback:

```python
# backend/services/langflow_client.py

def _run_single(self, store_id: str, scenario: str, use_explicit_prompt: bool = False) -> dict:
    url = f"{self.base_url}/api/v1/run/{self.flow_id}"
    tweaks = {...}
    response = requests.post(url, json=payload, headers=self.headers, timeout=120)
    response.raise_for_status()

    parsed_response = response.json()
    validated = self._parse_response(parsed_response)

    # TAMBAHAN: ekstrak decision_data mentah dari Langflow response
    # (output dari node Decision Engine, sebelum masuk ke LLM)
    decision_data = self._extract_decision_data(parsed_response)
    validated["decision_data"] = decision_data  # selalu disertakan

    return validated

def _extract_decision_data(self, response: dict) -> dict:
    """
    Ambil output Decision Engine node dari Langflow response,
    terlepas dari apakah LLM formatting berhasil atau tidak.
    """
    try:
        # Sesuaikan path ini dengan struktur aktual response Langflow —
        # cek di response["outputs"][0]["outputs"] untuk node Decision Engine
        for output in response["outputs"][0]["outputs"]:
            if output.get("component_display_name") == "Decision Engine":
                return json.loads(output["results"]["data"]["text"])
    except (KeyError, IndexError, json.JSONDecodeError):
        pass
    return {}
```

**Langkah 2** — `_build_fallback` di `LangflowClient` juga harus meneruskan `decision_data`:

```python
def _build_fallback(self, last_result: dict | None) -> dict:
    decision_data = last_result.get("decision_data", {}) if last_result else {}
    return {
        "valid": False,
        "parsed": last_result.get("parsed") if last_result else None,
        "reason": "max_retries_exceeded",
        "missing_numbers": last_result.get("missing_numbers", []) if last_result else [],
        "decision_data": decision_data,  # TAMBAHAN
        "_fallback_used": True,
    }
```

**Langkah 3** — `alert_service.py` menggunakan `generate_fallback_message` yang sudah benar, hapus `_build_fallback_message` yang generik:

```python
# backend/services/alert_service.py
from langflow.logic.output_validator import generate_fallback_message  # TAMBAHAN import

def send_alert(store_id: str, validated_output: dict) -> dict:
    ...
    is_valid = validated_output.get("valid", False)
    parsed = validated_output.get("parsed", {})

    if not is_valid or not parsed:
        decision_data = validated_output.get("decision_data", {})
        if decision_data:
            fallback = generate_fallback_message(decision_data)
            message = fallback["full_message"]
            button_text = fallback["action_button"]
        else:
            # Hanya sampai ke sini jika decision_data juga tidak tersedia —
            # kondisi darurat, seharusnya sangat jarang terjadi
            message = (
                "⚠️ Sistem mengalami gangguan saat memproses data toko Anda.\n"
                "Tim kami akan mengecek secara manual. Mohon maaf atas ketidaknyamanannya."
            )
            button_text = "Mengerti"
        model_used = "fallback_template"
    else:
        message = parsed.get("full_message", "")
        button_text = parsed.get("action_button", "Lihat Detail")
        model_used = LLM_MODEL_NAME
    ...

# HAPUS fungsi _build_fallback_message() — sudah digantikan generate_fallback_message()
```

### Acceptance Criteria
- [ ] `_build_fallback_message()` di `alert_service.py` dihapus total
- [ ] `generate_fallback_message()` dari `langflow/logic/output_validator.py` dipanggil di jalur produksi (`alert_service.py`)
- [ ] Test baru: paksa semua 3 retry gagal (mock `LangflowClient._run_single` untuk selalu return invalid), verifikasi pesan yang dikirim ke Telegram **mengandung angka kas dan runway asli**, bukan generik
- [ ] Test lama `test_fallback_message_structure` di `test_output_validator.py` tetap lulus tanpa perubahan
- [ ] Tambahkan test baru di `tests/test_integration_e2e.py`: `test_fallback_message_contains_real_numbers`

---

## FIX #2 (P0) — Output Validator Tidak Cek Angka Restock

### Masalah
`_extract_critical_numbers()` di `langflow/logic/output_validator.py` hanya mengecek `current_cash`, `net_amount` per settlement, dan `amount` untuk `collect_receivable`. Untuk `pending_decision.type == "restock"`, field `cost` **tidak pernah divalidasi**. Ini berarti skenario S2 dan S4 (2 dari 5 skenario) bisa lolos validasi meski LLM salah menyebutkan atau menghilangkan biaya restock.

### Kode Saat Ini (Tidak Lengkap)
```python
# langflow/logic/output_validator.py
def _extract_critical_numbers(decision_data: dict) -> list:
    numbers = []
    if decision_data.get("current_cash", 0) > 10000:
        numbers.append(int(decision_data["current_cash"]))
    for s in decision_data.get("settlements", []):
        if s.get("net_amount", 0) > 10000:
            numbers.append(int(s["net_amount"]))
    decision = decision_data.get("pending_decision")
    if decision and decision.get("type") == "collect_receivable":
        if decision.get("amount", 0) > 10000:
            numbers.append(int(decision["amount"]))
    return numbers
```

### Perbaikan
```python
# langflow/logic/output_validator.py
def _extract_critical_numbers(decision_data: dict) -> list:
    numbers = []
    if decision_data.get("current_cash", 0) > 10000:
        numbers.append(int(decision_data["current_cash"]))
    for s in decision_data.get("settlements", []):
        if s.get("net_amount", 0) > 10000:
            numbers.append(int(s["net_amount"]))

    decision = decision_data.get("pending_decision")
    if decision:
        decision_type = decision.get("type")

        if decision_type == "collect_receivable":
            if decision.get("amount", 0) > 10000:
                numbers.append(int(decision["amount"]))

        elif decision_type == "restock":
            # TAMBAHAN: validasi cost restock
            if decision.get("cost", 0) > 10000:
                numbers.append(int(decision["cost"]))
            # Jika best_settlement ada, net_amount-nya juga harus tervalidasi
            # (sudah tercakup dari loop settlements di atas, tapi pastikan konsisten)

    return numbers
```

### Kenapa Ini Penting
Prinsip #1 di `ARCHITECTURE_BOUNDARIES.md`: *"LLM tidak pernah menyentuh angka mentah... setiap output LLM divalidasi sebelum dikirim."* Validasi yang tidak lengkap sama saja dengan tidak ada validasi untuk skenario yang tidak tercakup.

### Acceptance Criteria
- [ ] `_extract_critical_numbers()` mengecek `cost` untuk decision type `restock`
- [ ] Test baru di `tests/test_output_validator.py`: `test_missing_restock_cost_number` — buat `full_message` yang tidak menyebutkan biaya restock, verifikasi `valid == False` dan `cost` masuk ke `missing_numbers`
- [ ] Jalankan ulang `tests/test_integration_pipeline.py::test_s2_waspada` dan `test_s4` (jika ada) — pastikan tidak ada regresi

---

## FIX #3 (P1) — System Prompt Dasar Tidak Sinkron dengan Retry Prompt

### Masalah
`SPRINT_REPORT.md` Section 3.1 mengklaim system prompt sudah diupdate dengan aturan "sebutkan net amount individual", tapi aturan itu hanya ada di `RETRY_SYSTEM_PROMPT` (dipakai mulai attempt ke-2), bukan di file dasar `langflow/prompts/message_formatter_system_prompt.md` (dipakai di attempt pertama). Akibatnya attempt pertama untuk skenario multi-settlement kemungkinan besar selalu gagal dan baru berhasil di attempt kedua — buang 1 API call + 2 detik jeda setiap kali.

### Perbaikan
Satukan kedua prompt menjadi satu sumber kebenaran. Update file dasar dengan aturan yang sama:

```markdown
<!-- langflow/prompts/message_formatter_system_prompt.md -->
Kamu adalah asisten keuangan untuk pemilik toko online Indonesia.

Tugasmu SATU: ubah data JSON yang diberikan menjadi pesan Telegram yang singkat,
jelas, dan mudah dipahami pemilik toko yang sibuk.

ATURAN WAJIB:
1. JANGAN ubah angka sama sekali — tampilkan persis seperti di data
2. Format angka dengan titik sebagai pemisah ribuan (contoh: Rp 11.010.000)
3. Maksimal 8 baris pesan
4. Gunakan emoji secukupnya — jangan berlebihan
5. Selalu sertakan field "action_button" — satu aksi paling penting untuk user
6. Jika ada lebih dari satu settlement, WAJIB sebutkan net amount masing-masing
   secara individual — JANGAN dijumlah menjadi total saja
7. WAJIB sebutkan saldo kas saat ini (current_cash) di full_message
8. Jika ada pending_decision bertipe "restock", WAJIB sebutkan angka "cost"-nya
   secara eksplisit di full_message

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

Lalu di `backend/services/langflow_client.py`, **hapus duplikasi** `RETRY_SYSTEM_PROMPT` dan baca dari file yang sama:

```python
# backend/services/langflow_client.py
from pathlib import Path

PROMPT_PATH = Path(__file__).parent.parent.parent / "langflow" / "prompts" / "message_formatter_system_prompt.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")

# HAPUS definisi RETRY_SYSTEM_PROMPT yang terpisah.
# Gunakan SYSTEM_PROMPT yang sama untuk semua attempt — karena sekarang
# aturan multi-settlement dan restock cost sudah ada di attempt pertama.
```

Sesuaikan `_run_single()` agar tidak lagi membedakan `use_explicit_prompt` (karena base prompt sudah cukup eksplisit dari attempt pertama). Retry logic tetap dipertahankan untuk kasus lain (timeout, invalid JSON, dll) — hanya bagian "ganti ke prompt lebih eksplisit" yang dihapus karena sekarang tidak diperlukan.

### Acceptance Criteria
- [ ] Hanya ada SATU sumber system prompt (`langflow/prompts/message_formatter_system_prompt.md`), tidak ada duplikasi string di Python
- [ ] `langflow_client.py` membaca prompt dari file, bukan hardcoded string
- [ ] Jalankan ulang mini spike test (5 skenario × 1 attempt, tanpa retry) — target: skor multi-settlement (S5) naik dari yang sebelumnya butuh retry, sekarang lolos di attempt pertama
- [ ] Update `SPRINT_REPORT.md` Section 3.1 agar sesuai kondisi baru (satu prompt, bukan dua)

---

## FIX #4 (P1) — Loop Follow-up Tidak Pernah Berjalan

### Masalah
Tabel `pending_triggers` ada di schema (`backend/database.py`) tapi tidak pernah di-insert, dibaca, atau diupdate di manapun dalam codebase. Ketika user klik "✅ Confirm" di Telegram, sistem hanya mencatat status dan berkata "sampai besok" — tidak ada follow-up proaktif meski keputusan yang dikonfirmasi (misal: restock setelah settlement cair) butuh tindak lanjut nyata.

Ini bertentangan dengan konsep inti produk kita: agent yang **terus memantau** sampai kondisi berubah, bukan yang berhenti setelah satu notifikasi.

### Yang Harus Dibangun

**Langkah 1** — Saat `Decision Engine` menghasilkan keputusan bertipe `restock` dengan `best_settlement` yang punya tanggal di masa depan, dan user klik confirm, buat entry di `pending_triggers`:

```python
# backend/services/telegram_webhook.py

from backend.database import get_db_path
import sqlite3
import json

async def _handle_confirm(query, store_id: str):
    """User klik ✅ — tandai sudah dibaca DAN buat trigger follow-up jika relevan."""
    save_user_action(store_id, "confirmed")

    # TAMBAHAN: ambil decision data dari alert terakhir, buat trigger jika perlu
    last_decision = _get_last_decision_data(store_id)
    if last_decision and last_decision.get("pending_decision"):
        decision = last_decision["pending_decision"]
        if decision.get("type") == "restock" and decision.get("best_settlement"):
            _create_pending_trigger(
                store_id=store_id,
                trigger_type="restock_after_settlement",
                condition_data={
                    "settlement_id": decision["best_settlement"]["settlement_id"],
                    "expected_date": decision["best_settlement"]["disbursement_date"],
                    "item": decision["item"],
                    "cost": decision["cost"],
                }
            )

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(
        "✅ Noted! Alert sudah dikonfirmasi.\n"
        "Saya akan pantau dan kabari begitu settlement cair."  # UBAH pesan
    )


def _create_pending_trigger(store_id: str, trigger_type: str, condition_data: dict):
    conn = sqlite3.connect(get_db_path())
    conn.execute(
        """
        INSERT INTO pending_triggers (store_id, trigger_type, condition_data, is_resolved)
        VALUES (?, ?, ?, ?)
        """,
        (store_id, trigger_type, json.dumps(condition_data), False),
    )
    conn.commit()
    conn.close()


def _get_last_decision_data(store_id: str) -> dict | None:
    """Ambil decision_data dari alert terakhir — perlu FIX #1 selesai dulu
    karena field ini baru ada setelah decision_data disimpan di alert_history."""
    # Catatan: butuh kolom baru `decision_data` (JSON) di tabel alert_history
    # jika belum ada — lihat "Perubahan Schema yang Diperlukan" di bawah
    ...
```

**Langkah 2** — Tambahkan fungsi resolver yang dipanggil setiap kali `daily_monitor.py` jalan, untuk mengecek apakah ada trigger yang kondisinya sudah terpenuhi:

```python
# backend/scheduler/trigger_resolver.py  (FILE BARU)
import sqlite3
import json
from datetime import datetime
from backend.database import get_db_path
from backend.services.alert_service import send_followup_alert  # perlu ditambahkan


def resolve_pending_triggers():
    """
    Dipanggil setiap kali daily_monitor jalan.
    Cek semua pending_triggers yang belum resolved,
    bandingkan dengan kondisi hari ini, kirim follow-up jika terpenuhi.
    """
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM pending_triggers WHERE is_resolved = FALSE"
    ).fetchall()

    today = datetime.now().date().isoformat()

    for row in rows:
        condition = json.loads(row["condition_data"])

        if row["trigger_type"] == "restock_after_settlement":
            if condition["expected_date"] <= today:
                # Settlement seharusnya sudah cair — kirim follow-up
                send_followup_alert(
                    store_id=row["store_id"],
                    message=(
                        f"💰 Settlement sudah waktunya cair.\n"
                        f"Aman untuk restock {condition['item']} "
                        f"(Rp {condition['cost']:,})".replace(",", ".")
                    )
                )
                _mark_resolved(conn, row["id"])

    conn.close()


def _mark_resolved(conn, trigger_id: int):
    conn.execute(
        "UPDATE pending_triggers SET is_resolved = TRUE WHERE id = ?",
        (trigger_id,)
    )
    conn.commit()
```

**Langkah 3** — Panggil `resolve_pending_triggers()` di awal `run_daily_monitoring()`:

```python
# backend/scheduler/daily_monitor.py
from backend.scheduler.trigger_resolver import resolve_pending_triggers

def run_daily_monitoring(scenario_override: str | None = None):
    ...
    resolve_pending_triggers()  # TAMBAHAN — cek trigger sebelum monitoring rutin
    ...
```

### Perubahan Schema yang Diperlukan
Tambahkan kolom `decision_data` (JSON, nullable) ke tabel `alert_history` agar `_get_last_decision_data()` bisa bekerja:

```sql
ALTER TABLE alert_history ADD COLUMN decision_data TEXT;
```

Update `_save_alert_history()` di `alert_service.py` untuk menyimpan `decision_data` sebagai JSON string setiap kali alert dikirim.

### Catatan Penting untuk MVP
Karena data settlement di sprint ini masih **mock**, "settlement sudah cair" tidak bisa dicek dari rekening sungguhan. Untuk MVP, `resolve_pending_triggers()` cukup membandingkan tanggal hari ini dengan `expected_date` dari mock data. Ini SUDAH CUKUP untuk mendemokan konsepnya ke juri — jangan over-engineer dengan mencoba integrasi real payment gateway di sprint ini.

### Acceptance Criteria
- [ ] Kolom `decision_data` ditambahkan ke `alert_history`
- [ ] Klik "Confirm" pada alert bertipe restock membuat entry baru di `pending_triggers`
- [ ] `resolve_pending_triggers()` berjalan setiap kali `run_daily_monitoring()` dipanggil
- [ ] Test baru: simulasikan trigger dengan `expected_date` = kemarin, jalankan `resolve_pending_triggers()`, verifikasi follow-up alert terkirim dan `is_resolved` jadi `TRUE`
- [ ] Update pesan konfirmasi Telegram agar mencerminkan bahwa agent akan follow-up, bukan "sampai besok"

---

## FIX #5 (P2) — Implementasi `flash_sale` Decision Type

### Masalah
`KNOWN_GAPS.md` sudah mencatat ini sebagai scope sprint berikutnya. Mock data S4 di implementasi aktual (`S4_RESTOCK_AMAN`) berbeda dari S4 di spike test asli (skenario flash sale) — kapabilitas ini belum pernah dibangun sama sekali, padahal sudah tervalidasi di level prompt/LLM.

### Spesifikasi yang Harus Diimplementasikan

**Threshold yang harus didefinisikan** (sebagai konstanta Python, sesuai prinsip arsitektur):
```python
# langflow/logic/decision_engine.py
FLASH_SALE_MIN_CASH_BUFFER = 2_000_000  # kas minimum yang harus tersisa setelah ikut flash sale
FLASH_SALE_MAX_STOCK_BUDGET_RATIO = 0.5  # budget stok tambahan maks 50% dari kas saat ini
```

**Logic yang harus ditambahkan:**
```python
def make_decision(risk_data: dict) -> dict:
    pending_decision = None
    status = risk_data["status"]

    # ... (logic collect_receivable dan restock yang sudah ada) ...

    # TAMBAHAN: flash sale evaluation
    flash_sale_opportunity = risk_data.get("flash_sale_opportunity")
    if flash_sale_opportunity and status == "AMAN" and pending_decision is None:
        pending_decision = _evaluate_flash_sale(risk_data, flash_sale_opportunity)

    return {...}


def _evaluate_flash_sale(risk_data: dict, opportunity: dict) -> dict:
    current_cash = risk_data["current_cash_balance"]
    stock_budget = opportunity["required_stock_budget"]
    cash_after = current_cash - stock_budget

    can_join = (
        cash_after >= FLASH_SALE_MIN_CASH_BUFFER
        and stock_budget <= current_cash * FLASH_SALE_MAX_STOCK_BUDGET_RATIO
    )

    recommendation = (
        f"IKUT flash sale {opportunity['platform']} — kas tetap aman "
        f"(sisa Rp {cash_after:,})".replace(",", ".")
        if can_join else
        f"TUNGGU dulu — ikut flash sale akan menyisakan kas hanya "
        f"Rp {cash_after:,}, terlalu tipis".replace(",", ".")
    )

    return {
        "type": "flash_sale",
        "platform": opportunity["platform"],
        "date": opportunity["date"],
        "estimated_revenue_uplift": opportunity["estimated_revenue_uplift"],
        "required_stock_budget": stock_budget,
        "cash_after_joining": cash_after,
        "can_join": can_join,
        "recommendation": recommendation,
    }
```

**Tambahkan skenario mock baru** `S6_FLASH_SALE` ke `store_scenarios.json` — gunakan data dari skenario S4 di spike test original (`SPIKE_TEST_RESULTS.md`) sebagai referensi, karena datanya sudah tervalidasi model-nya:
```json
"S6_FLASH_SALE": {
  "description": "Kas sehat, ada flash sale besok, perlu keputusan ikut atau tidak",
  "data": {
    "store_id": "toko_andi_001",
    "owner_name": "Pak Deni",
    "current_cash_balance": 12400000,
    "average_daily_expense": 560000,
    "settlements": [...],
    "overdue_receivables": [],
    "pending_stock_need": null,
    "flash_sale_opportunity": {
      "platform": "Shopee",
      "date": "2026-09-23",
      "estimated_revenue_uplift": 8000000,
      "required_stock_budget": 4500000
    }
  }
}
```

**Update Output Validator** — tambahkan validasi untuk field flash sale:
```python
# langflow/logic/output_validator.py
elif decision_type == "flash_sale":
    if decision.get("required_stock_budget", 0) > 10000:
        numbers.append(int(decision["required_stock_budget"]))
    if decision.get("cash_after_joining", 0) > 10000:
        numbers.append(int(decision["cash_after_joining"]))
```

### Acceptance Criteria
- [ ] `_evaluate_flash_sale()` diimplementasikan dengan threshold sebagai konstanta
- [ ] Skenario `S6_FLASH_SALE` ditambahkan ke mock data
- [ ] Output Validator memvalidasi angka-angka spesifik flash sale
- [ ] Test baru di `tests/test_integration_pipeline.py`: `test_s6_flash_sale_can_join` dan `test_s6_flash_sale_cannot_join` (buat 2 variasi data — satu yang aman diikuti, satu yang tidak)
- [ ] End-to-end test: jalankan skenario ini via `/trigger/scenario/S6_FLASH_SALE`, verifikasi pesan Telegram berisi rekomendasi ikut/tidak dengan angka yang benar

---

## FIX #6 (P2) — Implementasi `multiple` Decision Type

### Masalah
Saat ini jika KRITIS + ada piutang, sistem hanya menampilkan `collect_receivable` dan mengabaikan kebutuhan restock yang mungkin juga aktif bersamaan. Ini kehilangan informasi penting yang sebenarnya relevan untuk user.

### Spesifikasi

```python
# langflow/logic/decision_engine.py

def make_decision(risk_data: dict) -> dict:
    status = risk_data["status"]
    overdue = risk_data.get("overdue_receivables", [])
    stock_need = risk_data.get("pending_stock_need")
    flash_sale_opportunity = risk_data.get("flash_sale_opportunity")

    active_decisions = []

    if status == "KRITIS" and overdue:
        active_decisions.append(_build_collect_receivable_decision(overdue))

    if stock_need:
        active_decisions.append(
            _build_restock_decision(
                _find_settlement_before(risk_data["settlements_net"], stock_need["stock_depletes_on"]),
                stock_need,
                status
            )
        )

    if flash_sale_opportunity and status == "AMAN":
        active_decisions.append(_evaluate_flash_sale(risk_data, flash_sale_opportunity))

    if len(active_decisions) == 0:
        pending_decision = None
    elif len(active_decisions) == 1:
        pending_decision = active_decisions[0]
    else:
        # TAMBAHAN: multiple
        pending_decision = _build_multiple_decision(active_decisions, status)

    return {...}


def _build_multiple_decision(decisions: list, status: str) -> dict:
    """
    Urutkan berdasarkan prioritas: collect_receivable > restock > flash_sale
    saat status KRITIS/WASPADA. Field 'priority_N' untuk LLM merangkai narasi.
    """
    priority_order = {"collect_receivable": 0, "restock": 1, "flash_sale": 2}
    sorted_decisions = sorted(decisions, key=lambda d: priority_order.get(d["type"], 99))

    result = {"type": "multiple", "decisions": sorted_decisions}
    for i, d in enumerate(sorted_decisions, start=1):
        result[f"priority_{i}"] = d["recommendation"]

    return result
```

**Update Output Validator** untuk tipe `multiple` — validasi semua angka dari SETIAP decision di dalam list:
```python
elif decision_type == "multiple":
    for sub_decision in decision.get("decisions", []):
        sub_type = sub_decision.get("type")
        if sub_type == "collect_receivable" and sub_decision.get("amount", 0) > 10000:
            numbers.append(int(sub_decision["amount"]))
        elif sub_type == "restock" and sub_decision.get("cost", 0) > 10000:
            numbers.append(int(sub_decision["cost"]))
        elif sub_type == "flash_sale":
            if sub_decision.get("required_stock_budget", 0) > 10000:
                numbers.append(int(sub_decision["required_stock_budget"]))
```

**Skenario mock:** Gunakan ulang `S5_MULTI_SETTLEMENT` yang sudah ada — data itu sebenarnya sudah punya `pending_stock_need` DAN `overdue_receivables` sekaligus, tapi saat ini logic lama meng-override jadi cuma `collect_receivable` saja (lihat `KNOWN_GAPS.md`). Setelah fix ini, S5 otomatis akan menghasilkan `type: "multiple"`.

### Acceptance Criteria
- [ ] `_build_multiple_decision()` diimplementasikan dengan urutan prioritas yang jelas
- [ ] Output Validator memvalidasi angka dari setiap sub-decision di dalam `multiple`
- [ ] Test ulang `tests/test_integration_pipeline.py::test_s5_multi_settlement` — update assertion untuk mengecek `pending_decision["type"] == "multiple"` dan `len(pending_decision["decisions"]) == 2`
- [ ] Update system prompt (`message_formatter_system_prompt.md`) dengan instruksi eksplisit cara merangkai `priority_1`, `priority_2` menjadi `full_message` yang runtut

---

## Urutan Pengerjaan yang Disarankan

```
1. FIX #1 (fallback message)      — berdiri sendiri, tidak bergantung fix lain
2. FIX #2 (validasi restock cost) — berdiri sendiri
3. FIX #3 (sinkronisasi prompt)   — sebaiknya setelah #2, karena prompt perlu
                                     menyebut aturan restock cost juga
4. FIX #5 (flash sale)            — sebaiknya sebelum #6, karena #6 butuh
                                     flash_sale sebagai salah satu sub-decision
5. FIX #6 (multiple)              — bergantung pada #5 selesai
6. FIX #4 (loop follow-up)        — independen, tapi butuh FIX #1 selesai dulu
                                     (butuh decision_data tersimpan di alert_history)
```

---

## Definition of Done — Sprint Perbaikan Ini

- [ ] Semua 6 fix di atas selesai dengan Acceptance Criteria masing-masing terpenuhi
- [ ] Total test suite bertambah dari 42 menjadi minimal 42 + 8 (test baru dari tiap fix) = 50 test, semua PASSED
- [ ] Jalankan `/trigger/all-scenarios` mencakup S1–S6 (6 skenario, bukan 5), semua menghasilkan alert Telegram yang valid
- [ ] `SPRINT_REPORT.md` diupdate — tambahkan Section baru "11. Bug Fix Round 1" yang mendokumentasikan keenam fix ini dengan cara yang sama seperti Section 3 (Deviasi) di laporan asli
- [ ] `KNOWN_GAPS.md` diupdate — hapus item yang sudah selesai (`flash_sale`, `multiple`), catat gap baru jika ditemukan selama pengerjaan
- [ ] Tidak ada fungsi mati baru (setiap fungsi yang ditulis harus benar-benar dipanggil di jalur eksekusi produksi — pelajaran dari FIX #1)

---

*Dokumen ini disusun berdasarkan review langsung terhadap kode di repo `settlement-intelligence-agent` v1.0.0-mvp. Jika AI coding assistant menemukan struktur kode yang berbeda dari yang dikutip di sini (misal karena sudah ada perubahan lain), sesuaikan pendekatan tapi pertahankan tujuan Acceptance Criteria yang sama.*
