# Spike Test Results — LLM Model Validation
## Marketplace Settlement Intelligence Agent

**Tanggal:** 21 September 2026
**Tujuan:** Validasi model Groq mana yang cukup akurat untuk memformat structured financial data menjadi pesan Telegram Bahasa Indonesia.

---

## Metodologi

3 model × 5 skenario = 15 test case. Setiap response dievaluasi dengan 5 kriteria (1 poin masing-masing, max 5 poin/skenario):

1. JSON valid dan bisa di-parse
2. Semua required fields ada
3. Angka kritis dari input tidak berubah di output
4. Menggunakan Bahasa Indonesia natural
5. Panjang pesan wajar (50–600 karakter)

---

## Hasil

| Model | Skor | JSON Valid | Angka Terjaga | Avg Response Time |
|---|---|---|---|---|
| **`groq/compound-mini`** | **25/25 (100%)** | 5/5 | 5/5 | 2.39s |
| `qwen/qwen3.8-27b` | 22/25 (88%) | 5/5 | 4/5 | 2.21s |
| `openai/gpt-oss-20b` | 19/25 (76%) | 4/5 | 4/5 | 1.17s |

---

## Temuan Kritis Per Model

### groq/compound-mini — PRIMARY
Tidak ada kegagalan di skenario manapun, termasuk S5 (skenario multi-masalah dengan 2 settlement + piutang tertunggak + settlement terlambat). Semua angka individual per marketplace muncul benar di output. Response time konsisten 2.2–2.5s — acceptable untuk agent yang jalan sekali sehari.

### qwen/qwen3.8-27b — FALLBACK dengan syarat
Gagal di S5: dua nilai settlement (Rp 6.800.000 dari Shopee dan Rp 3.200.000 dari Tokopedia) tidak muncul individual di `full_message` — hanya muncul sebagai total gabungan Rp 10.000.000. Untuk produk yang menjanjikan transparansi per marketplace, ini adalah cacat fungsional. Model ini juga sempat menunjukkan response time 8.68s di satu request (S3) — kemungkinan extended thinking — yang tidak konsisten dengan request lain di bawah 1 detik.

**Jika dipakai sebagai fallback:** wajib tambahkan validasi yang mengecek setiap nilai settlement individual muncul di output, bukan hanya total agregat.

### openai/gpt-oss-20b — EXCLUDED
Gagal total di S1 — response terpotong di tengah JSON (`"key_decision":` lalu berhenti). Ini bukan kesalahan format yang bisa diperbaiki dengan prompt engineering — ini adalah truncation, kemungkinan besar karena `max_tokens` yang tidak cukup atau model menghasilkan output yang lebih verbose dari model lain untuk skenario yang sama. Kegagalan jenis ini paling berbahaya karena berarti **alert tidak terkirim sama sekali** ke user, tanpa pemberitahuan.

---

## Keputusan Final

```
PRIMARY MODEL   : groq/compound-mini
FALLBACK MODEL  : qwen/qwen3.8-27b (dengan validasi ekstra wajib)
EXCLUDED        : openai/gpt-oss-20b
```

**Konfigurasi yang tervalidasi:**
- `temperature: 0.1` — rendah untuk konsistensi
- `response_format: {"type": "json_object"}` — mencegah invalid JSON
- `max_tokens: 800` — cukup untuk semua skenario yang ditest

---

## Rate Limit Awareness

`groq/compound-mini` memiliki limit 250 requests/day di akun yang ditest. Untuk MVP hackathon (demo + testing) ini lebih dari cukup. Untuk production dengan banyak toko, perlu upgrade tier atau distribusi request across model.

---

## Dampak ke Arsitektur

Hasil ini mengkonfirmasi asumsi kunci di `ARCHITECTURE_BOUNDARIES.md`: dengan memisahkan kalkulasi (Python) dari formatting (LLM), produk ini **tidak bergantung pada LLM yang sangat canggih**. Model kecil yang gratis sudah cukup karena tugasnya sudah disederhanakan menjadi satu hal saja — reformat data yang sudah benar.

Lihat `SPRINT_SETTLEMENT_AGENT.md` Section 6–7 untuk implementasi teknis lengkap.
