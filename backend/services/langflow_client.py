# backend/services/langflow_client.py
import json
import time
from pathlib import Path

import requests

from backend.config import LANGFLOW_BASE_URL, LANGFLOW_API_KEY, LANGFLOW_FLOW_ID

GROQ_NODE_ID = "GroqModel-30Czk"
DATA_FETCHER_NODE_ID = "DataFetcher-bG60r"

# Satu sumber prompt — dibaca dari file, tidak hardcoded
PROMPT_PATH = Path(__file__).parent.parent.parent / "langflow" / "prompts" / "message_formatter_system_prompt.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


class LangflowClient:
    def __init__(self):
        self.base_url = LANGFLOW_BASE_URL
        self.flow_id = LANGFLOW_FLOW_ID
        self.headers = {"Content-Type": "application/json"}
        if LANGFLOW_API_KEY:
            self.headers["x-api-key"] = LANGFLOW_API_KEY

    def run_flow(
        self,
        store_id: str,
        scenario: str = "S1_AMAN",
        max_retries: int = 3,
    ) -> dict:
        """
        Jalankan flow dengan retry logic (max 3 attempt).
        Setiap attempt pakai prompt yang sama — sudah lengkap dari attempt pertama.
        Jika semua gagal: return fallback dengan decision_data asli.
        """
        last_result = None

        for attempt in range(1, max_retries + 1):
            try:
                result = self._run_single(store_id=store_id, scenario=scenario)

                if result.get("valid"):
                    if attempt > 1:
                        print(f"    ✅ Valid setelah retry ke-{attempt - 1}")
                    return result

                last_result = result
                missing = result.get("missing_numbers", [])
                reason = result.get("reason", "unknown")
                print(f"    ⚠️  Attempt {attempt}/{max_retries} invalid — reason: {reason}, missing: {missing}")

                if attempt < max_retries:
                    time.sleep(2)

            except requests.exceptions.Timeout:
                print(f"    ⏱️  Attempt {attempt}/{max_retries} timeout")
                if attempt == max_retries:
                    raise
                time.sleep(5 * attempt)

            except requests.exceptions.HTTPError as e:
                raise ValueError(f"Langflow error: {e}") from e

        print(f"    🔄 Semua {max_retries} attempt gagal — gunakan fallback template")
        return self._build_fallback(last_result)

    def _run_single(self, store_id: str, scenario: str) -> dict:
        """Jalankan satu kali call ke Langflow."""
        url = f"{self.base_url}/api/v1/run/{self.flow_id}"

        tweaks = {
            DATA_FETCHER_NODE_ID: {
                "store_id": store_id,
                "scenario": scenario,
            },
            GROQ_NODE_ID: {
                "system_message": SYSTEM_PROMPT,
            },
        }

        payload = {
            "input_value": store_id,
            "input_type": "text",
            "output_type": "text",
            "tweaks": tweaks,
        }

        response = requests.post(
            url,
            json=payload,
            headers=self.headers,
            timeout=120,
        )
        response.raise_for_status()
        raw = response.json()

        validated = self._parse_response(raw)
        validated["decision_data"] = self._extract_decision_data(raw)
        return validated

    def _parse_response(self, response: dict) -> dict:
        """Ekstrak output OutputValidator dari response Langflow."""
        try:
            outputs = response["outputs"][0]["outputs"][0]
            text = outputs["results"]["message"]["text"]
            return json.loads(text)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise ValueError(
                f"Gagal parse response Langflow: {e}\nRaw: {response}"
            ) from e

    def _extract_decision_data(self, response: dict) -> dict:
        """
        Ambil output Decision Engine dari Langflow response.
        Decision Engine output adalah Message (JSON string) — kita parse kembali.
        """
        try:
            for output in response["outputs"][0]["outputs"]:
                if output.get("component_display_name") == "Decision Engine":
                    raw_text = output["results"]["message"]["text"]
                    return json.loads(raw_text)
        except (KeyError, IndexError, json.JSONDecodeError, TypeError):
            pass
        return {}

    def _build_fallback(self, last_result: dict | None) -> dict:
        """Fallback ketika semua retry gagal — sertakan decision_data."""
        decision_data = last_result.get("decision_data", {}) if last_result else {}
        return {
            "valid": False,
            "parsed": last_result.get("parsed") if last_result else None,
            "reason": "max_retries_exceeded",
            "missing_numbers": last_result.get("missing_numbers", []) if last_result else [],
            "decision_data": decision_data,
            "_fallback_used": True,
        }

    def health_check(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            return r.status_code == 200
        except requests.exceptions.ConnectionError:
            return False