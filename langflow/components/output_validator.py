import json
import sys
from lfx.custom.custom_component.component import Component
from lfx.io import MessageInput, Output
from lfx.schema.message import Message


class OutputValidator(Component):
    display_name = "Output Validator"
    description = "Validasi output LLM — pastikan angka kritis tidak hilang"

    inputs = [
        MessageInput(name="llm_output", display_name="LLM Raw Output", required=True),
        MessageInput(name="decision_data", display_name="Decision Engine Output", required=True),
    ]

    outputs = [
        Output(display_name="Validated Output", name="validated", method="validate"),
    ]

    def validate(self) -> Message:
        decision_dict = json.loads(self.decision_data.text)
        result = self._validate_output(self.llm_output.text, decision_dict)
        # Embed decision_data agar backend bisa ambil
        result["decision_data"] = decision_dict
        self.status = result
        return Message(text=json.dumps(result, ensure_ascii=False))

    def _validate_output(self, llm_output: str, decision_data: dict) -> dict:
        REQUIRED_FIELDS = [
            "status_line", "incoming_funds", "key_decision",
            "full_message", "action_button"
        ]
        try:
            clean = llm_output.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(lines[1:-1])
            parsed = json.loads(clean)
        except json.JSONDecodeError as e:
            return {"valid": False, "parsed": None,
                    "reason": f"invalid_json: {e}", "missing_numbers": []}

        missing_fields = [f for f in REQUIRED_FIELDS if f not in parsed]
        if missing_fields:
            return {"valid": False, "parsed": parsed,
                    "reason": f"missing_fields: {missing_fields}", "missing_numbers": []}

        full_message = parsed.get("full_message", "")
        critical_numbers = self._extract_critical_numbers(decision_data)
        missing_numbers = [
            n for n in critical_numbers
            if f"{n:,}".replace(",", ".") not in full_message
        ]
        if missing_numbers:
            return {"valid": False, "parsed": parsed,
                    "reason": "missing_numbers", "missing_numbers": missing_numbers}

        return {"valid": True, "parsed": parsed, "reason": None, "missing_numbers": []}

    def _extract_critical_numbers(self, decision_data: dict) -> list:
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
                if decision.get("cost", 0) > 10000:
                    numbers.append(int(decision["cost"]))

            elif decision_type == "flash_sale":
                if decision.get("required_stock_budget", 0) > 10000:
                    numbers.append(int(decision["required_stock_budget"]))
                if decision.get("cash_after_joining", 0) > 10000:
                    numbers.append(int(decision["cash_after_joining"]))

            elif decision_type == "multiple":
                for sub in decision.get("decisions", []):
                    sub_type = sub.get("type")
                    if sub_type == "collect_receivable" and sub.get("amount", 0) > 10000:
                        numbers.append(int(sub["amount"]))
                    elif sub_type == "restock" and sub.get("cost", 0) > 10000:
                        numbers.append(int(sub["cost"]))
                    elif sub_type == "flash_sale":
                        if sub.get("required_stock_budget", 0) > 10000:
                            numbers.append(int(sub["required_stock_budget"]))

        return numbers

    def build(self):
        return self.validate