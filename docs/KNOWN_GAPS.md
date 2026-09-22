# Known Gaps — Sprint 1

## Decision Engine

### flash_sale (belum diimplementasikan)
Sprint document menyebutkan `type: "flash_sale"` sebagai kemungkinan output
Decision Engine, tapi tidak ada spesifikasi detail dan tidak ada skenario mock
yang menggunakannya. Scope sprint berikutnya.

**Kondisi trigger yang direncanakan:**
- Stok menumpuk (belum didefinisikan threshold-nya)
- Kas cukup untuk absorb diskon
- Ada slot flash sale di marketplace

### multiple (belum diimplementasikan)
Tipe `multiple` untuk menggabungkan beberapa keputusan aktif sekaligus.
Contoh: WASPADA + butuh restock + ada piutang jatuh tempo → satu alert dengan
dua rekomendasi.

Saat ini jika ada dua kondisi, Decision Engine menggunakan prioritas:
KRITIS + piutang → `collect_receivable` (override restock).

**Yang perlu dibangun:**
- Logic untuk deteksi multiple conditions aktif bersamaan
- Format output `multiple` yang bisa diparsing LLM dengan benar
- Skenario mock S6 untuk test

## Mock Data vs Real API

Field yang disederhanakan untuk MVP:
- `commission_rate` → real API memberikan `commission_amount` langsung (bukan rate)
- `average_daily_expense` → tidak ada di API, harus diinput manual atau dihitung dari history
- Struktur real API adalah per-transaksi, bukan per-periode settlement yang sudah diagregasi
- TikTok Shop punya fee tambahan: affiliate commission, shipping insurance — diabaikan di MVP

Saat swap ke real API (ganti DataFetcher saja):
- Tambahkan aggregation layer di DataFetcher untuk grouping transaksi per periode
- Hitung commission_amount dari response langsung (tidak perlu rate)
- Tambahkan field average_daily_expense dari input manual seller atau kalkulasi 30-day rolling average