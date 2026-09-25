# Known Gaps

## Status per Sprint

| Item | Sprint 1 | Bug Fix Round 1 |
|------|----------|-----------------|
| `flash_sale` decision type | ❌ Belum | ✅ Selesai |
| `multiple` decision type | ❌ Belum | ✅ Selesai |
| Fallback message kosong angka | ✅ Ada fungsi, ❌ tidak dipanggil | ✅ Selesai |
| Output validator tidak cek restock cost | ❌ | ✅ Selesai |
| System prompt tidak sinkron | ❌ | ✅ Selesai |
| Loop follow-up pending_triggers | ❌ Tabel ada, tidak dipakai | ✅ Selesai |

---

## Gap Aktif (Scope Sprint Berikutnya)

### Mock Data vs Real API

Field yang disederhanakan untuk MVP:
- `commission_rate` → real API memberikan `commission_amount` langsung (bukan rate)
- `average_daily_expense` → tidak ada di API marketplace, harus diinput manual atau dihitung dari history 30 hari
- Struktur real API adalah per-transaksi, bukan per-periode settlement yang sudah diagregasi
- TikTok Shop punya fee tambahan: affiliate commission, shipping insurance — diabaikan di MVP
- Tanggal mock data di-adjust secara otomatis via `_adjust_dates()` di `data_fetcher.py` agar selalu relatif ke hari ini — ini adalah workaround, bukan solusi permanen

Saat swap ke real API (ganti `DataFetcher` saja):
- Tambahkan aggregation layer untuk grouping transaksi per periode
- Hitung `commission_amount` dari response langsung (tidak perlu rate)
- Tambahkan field `average_daily_expense` dari input manual seller atau kalkulasi 30-day rolling average

### Infrastruktur

- **Real API marketplace** — butuh partner approval 2–8 minggu. Swap hanya di `DataFetcher` component, semua layer di atas tidak perlu berubah.
- **Webhook production** — saat ini pakai ngrok untuk development. Production butuh domain + SSL.
- **Multi-toko management** — database schema sudah mendukung multiple stores, tapi UI management belum ada.
- **Model LLM** — `groq/compound-mini` (primary dari spike test) sudah tidak tersedia. Saat ini pakai `qwen/qwen3.8-27b`. Monitor ketersediaan atau evaluasi Gemini Flash sebagai alternatif.

### Decision Engine — Gap yang Tersisa

- **Trigger follow-up non-restock** — `pending_triggers` saat ini hanya handle `restock_after_settlement`. Tipe trigger lain (collect_receivable follow-up, flash_sale reminder) belum diimplementasikan.
- **Flash sale opportunity** — saat ini diinput manual di mock data. Di production, perlu integrasi dengan API notifikasi flash sale dari marketplace.
- **Multiple decision dengan lebih dari 2 sub-decisions** — saat ini maksimal 2 (collect_receivable + restock). Kombinasi 3 keputusan aktif sekaligus belum ditest.