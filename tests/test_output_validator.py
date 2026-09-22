import json
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langflow.components.output_validator import validate_llm_output, generate_fallback_message


def _make_decision_data(cash=850_000, settlements=None):
    return {
        "store_owner": "Pak Andi",
        "store_id": "toko_andi_001",
        "status": "KRITIS",
        "urgency_level": 3,
        "current_cash": cash,
        "runway_days": 3,
        "min_balance_amount": -50_000,
        "settlements": settlements or [
            {"marketplace": "tiktok_shop", "net_amount": 4_320_000, "disbursement_date": "2026-09-28"}
        ],
        "total_incoming_this_week": 4_320_000,
        "pending_decision": None,
        "daily_projection": [],
    }


def _make_valid_llm_output(cash=850_000, net=4_320_000):
    return json.dumps({
        "status_line": f"⚠️ KRITIS – Kas Rp {cash:,}".replace(",", "."),
        "incoming_funds": f"💰 Dana: Rp {net:,}".replace(",", "."),
        "key_decision": "Tagih piutang hari ini",
        "full_message": (
            f"⚠️ KRITIS – Kas Rp {cash:,}, runway 3 hari\n"
            f"💰 Dana: Rp {net:,} (TikTok Shop)\n"
            f"📌 Tagih piutang hari ini"
        ).replace(",", "."),
        "action_button": "Tagih Sekarang",
    })


class TestOutputValidator:
    def test_valid_output(self):
        decision = _make_decision_data()
        llm_out = _make_valid_llm_output()
        result = validate_llm_output(llm_out, decision)
        assert result["valid"] is True
        assert result["parsed"] is not None
        assert result["missing_numbers"] == []

    def test_invalid_json(self):
        decision = _make_decision_data()
        result = validate_llm_output("ini bukan json {{{", decision)
        assert result["valid"] is False
        assert "invalid_json" in result["reason"]

    def test_missing_required_field(self):
        decision = _make_decision_data()
        incomplete = json.dumps({
            "status_line": "ok",
            "incoming_funds": "ok",
            # key_decision hilang
            "full_message": "Kas Rp 850.000",
            "action_button": "ok",
        })
        result = validate_llm_output(incomplete, decision)
        assert result["valid"] is False
        assert "missing_fields" in result["reason"]

    def test_missing_cash_number(self):
        """LLM output tidak menyertakan angka kas — harus gagal validasi."""
        decision = _make_decision_data(cash=850_000)
        # full_message tidak mengandung 850.000
        bad_output = json.dumps({
            "status_line": "⚠️ KRITIS",
            "incoming_funds": "💰 Dana: Rp 4.320.000",
            "key_decision": "Tagih piutang",
            "full_message": "⚠️ KRITIS – kondisi berbahaya\n💰 Dana: Rp 4.320.000",
            "action_button": "Tagih",
        })
        result = validate_llm_output(bad_output, decision)
        assert result["valid"] is False
        assert 850_000 in result["missing_numbers"]

    def test_missing_settlement_number(self):
        """Net settlement tidak muncul di output — harus gagal."""
        decision = _make_decision_data(
            cash=850_000,
            settlements=[
                {"marketplace": "tiktok_shop", "net_amount": 4_320_000, "disbursement_date": "2026-09-28"}
            ]
        )
        # full_message menyebut kas tapi TIDAK menyebut 4.320.000
        bad_output = json.dumps({
            "status_line": "⚠️ KRITIS – Kas Rp 850.000",
            "incoming_funds": "💰 Dana masuk minggu ini",  # angka hilang
            "key_decision": "Tagih piutang",
            "full_message": "⚠️ KRITIS – Kas Rp 850.000\n💰 Dana masuk minggu ini",
            "action_button": "Tagih",
        })
        result = validate_llm_output(bad_output, decision)
        assert result["valid"] is False
        assert 4_320_000 in result["missing_numbers"]

    def test_markdown_fence_cleaned(self):
        """LLM kadang kembalikan JSON dalam markdown fence — harus tetap valid."""
        decision = _make_decision_data()
        with_fence = "```json\n" + _make_valid_llm_output() + "\n```"
        result = validate_llm_output(with_fence, decision)
        assert result["valid"] is True

    def test_multi_settlement_both_numbers_required(self):
        """Skenario S5: dua settlement — keduanya harus muncul di output."""
        decision = _make_decision_data(
            cash=2_100_000,
            settlements=[
                {"marketplace": "shopee", "net_amount": 13_075_000, "disbursement_date": "2026-09-24"},
                {"marketplace": "tokopedia", "net_amount": 7_160_000, "disbursement_date": "2026-09-25"},
            ]
        )
        # Output yang hanya menyebut total (ini yang gagal di qwen)
        only_total = json.dumps({
            "status_line": "🟡 WASPADA – Kas Rp 2.100.000",
            "incoming_funds": "💰 Total dana: Rp 20.235.000",  # hanya total, tidak rinci
            "key_decision": "Restock setelah settlement",
            "full_message": "🟡 WASPADA – Kas Rp 2.100.000\n💰 Total dana: Rp 20.235.000\n📌 Restock setelah settlement",
            "action_button": "Cek Settlement",
        })
        result = validate_llm_output(only_total, decision)
        # 13.075.000 dan 7.160.000 harus masing-masing ada
        assert result["valid"] is False  # salah satu pasti missing

    def test_fallback_message_structure(self):
        """Fallback template harus punya semua required fields."""
        decision = _make_decision_data()
        fallback = generate_fallback_message(decision)
        required = ["status_line", "incoming_funds", "key_decision", "full_message", "action_button"]
        for field in required:
            assert field in fallback, f"Field '{field}' tidak ada di fallback"
        assert fallback["_fallback_used"] is True