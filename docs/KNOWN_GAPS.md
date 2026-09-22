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