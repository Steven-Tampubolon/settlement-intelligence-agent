"""
Layer 3A — Output Validator
BOLEH: Validasi output LLM — cek angka kritis tidak hilang/berubah
TIDAK BOLEH: Format ulang pesan, buat keputusan
"""
import json
from langflow.custom import CustomComponent


class OutputValidator(CustomComponent):
    display_name = "Output Validator"
    description = "Validasi output LLM — pastikan angka kritis dari source_data ada di pesan"

    def build_config(self):
        return {
            "llm_output": {
                "display_name": "LLM Raw Output (string)",
                "required": True,
            },
            "decision_data": {
                "display_name": "Decision Engine Output",
                "required": True,
            },
        }

    def build(self, llm_output: str, decision_data: dict) -> dict:
        return validate_llm_output(llm_output, decision_data)


# ── Fungsi standalone ─────────────────────────────────────────────────
def validate_llm_output(llm_output: str, decision_data: dict) -> dict:
    """
    Validasi dua hal:
    1. JSON valid dan punya semua required fields
    2. Semua angka kritis dari decision_data muncul di full_message

    Return:
    {
        "valid": bool,
        "parsed": dict | None,
        "reason": str | None,
        "missing_numbers": list,
        "retry_count": int  # diisi oleh caller
    }
    """
    REQUIRED_FIELDS = [
        "status_line",
        "incoming_funds",
        "key_decision",
        "full_message",
        "action_button",
    ]

    # Step 1: Parse JSON
    try:
        # Bersihkan jika ada markdown fence
        clean = llm_output.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1])
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "parsed": None,
            "reason": f"invalid_json: {str(e)}",
            "missing_numbers": [],
        }

    # Step 2: Cek required fields
    missing_fields = [f for f in REQUIRED_FIELDS if f not in parsed]
    if missing_fields:
        return {
            "valid": False,
            "parsed": parsed,
            "reason": f"missing_fields: {missing_fields}",
            "missing_numbers": [],
        }

    # Step 3: Validasi angka kritis
    full_message = parsed.get("full_message", "")
    critical_numbers = _extract_critical_numbers(decision_data)
    missing_numbers = []

    for n in critical_numbers:
        # Format angka dengan titik sebagai pemisah ribuan (format Indonesia)
        formatted = f"{n:,}".replace(",", ".")
        if formatted not in full_message:
            missing_numbers.append(n)

    if missing_numbers:
        return {
            "valid": False,
            "parsed": parsed,
            "reason": "missing_numbers",
            "missing_numbers": missing_numbers,
        }

    return {
        "valid": True,
        "parsed": parsed,
        "reason": None,
        "missing_numbers": [],
    }


def _extract_critical_numbers(decision_data: dict) -> list[int]:
    """
    Kumpulkan semua angka kritis yang HARUS muncul di output LLM.
    Threshold: angka > 10.000 (bawah ini tidak signifikan untuk divalidasi).
    """
    numbers = []

    # Saldo kas saat ini
    if decision_data.get("current_cash", 0) > 10000:
        numbers.append(int(decision_data["current_cash"]))

    # Net amount per settlement
    for s in decision_data.get("settlements", []):
        if s.get("net_amount", 0) > 10000:
            numbers.append(int(s["net_amount"]))

    # Angka dari keputusan pending
    decision = decision_data.get("pending_decision")
    if decision:
        for key in ["amount", "cost"]:
            if decision.get(key, 0) > 10000:
                numbers.append(int(decision[key]))

        # Jika multi_action, ambil dari sub-keputusan juga
        if decision.get("type") == "multi_action":
            restock = decision.get("restock", {})
            if restock.get("cost", 0) > 10000:
                numbers.append(int(restock["cost"]))

    return numbers


def generate_fallback_message(decision_data: dict) -> dict:
    """
    Template Python murni sebagai fallback jika LLM gagal 2x retry.
    Output-nya identik strukturnya dengan output LLM normal.
    """
    status = decision_data["status"]
    cash = decision_data["current_cash"]
    runway = decision_data["runway_days"]
    owner = decision_data["store_owner"]

    # Format angka Indonesia
    cash_fmt = f"Rp {cash:,}".replace(",", ".")

    # Status line
    emoji_map = {"KRITIS": "⚠️", "WASPADA": "🟡", "AMAN": "✅"}
    emoji = emoji_map.get(status, "ℹ️")
    status_line = f"{emoji} {status} – Kas {cash_fmt}, runway {runway} hari"

    # Settlement summary
    settlements = decision_data.get("settlements", [])
    incoming_parts = []
    for s in settlements:
        net_fmt = f"Rp {s['net_amount']:,}".replace(",", ".")
        incoming_parts.append(f"{s['marketplace'].title()} {net_fmt} ({s['disbursement_date']})")
    incoming_funds = "Dana masuk: " + ", ".join(incoming_parts) if incoming_parts else "Tidak ada dana masuk dalam 14 hari"

    # Key decision
    decision = decision_data.get("pending_decision")
    if decision:
        key_decision = decision.get("recommendation", "Pantau kondisi kas")
    else:
        key_decision = "Kondisi aman, pantau terus"

    full_message = f"{status_line}\n{incoming_funds}\n📌 {key_decision}"

    return {
        "status_line": status_line,
        "incoming_funds": incoming_funds,
        "key_decision": key_decision,
        "full_message": full_message,
        "action_button": "Lihat Detail",
        "_fallback_used": True,
    }