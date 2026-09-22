# backend/services/langflow_client.py
import json
import time
import requests
from backend.config import LANGFLOW_BASE_URL, LANGFLOW_API_KEY, LANGFLOW_FLOW_ID


class LangflowClient:
    def __init__(self):
        self.base_url = LANGFLOW_BASE_URL
        self.flow_id = LANGFLOW_FLOW_ID
        self.headers = {"Content-Type": "application/json"}
        if LANGFLOW_API_KEY:
            self.headers["x-api-key"] = LANGFLOW_API_KEY

    def run_flow(self, store_id: str, scenario: str = "S1_AMAN", max_retries: int = 3) -> dict:
        url = f"{self.base_url}/api/v1/run/{self.flow_id}"
        payload = {
            "input_value": store_id,
            "input_type": "text",
            "output_type": "text",
            "tweaks": {
                "DataFetcher-bG60r": {
                    "store_id": store_id,
                    "scenario": scenario,
                }
            },
        }

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(url, json=payload, headers=self.headers, timeout=120)
                response.raise_for_status()
                return self._parse_response(response.json())
            except requests.exceptions.Timeout:
                if attempt == max_retries:
                    raise
                print(f"Timeout attempt {attempt}/{max_retries}, retry...")
                time.sleep(5 * attempt)
            except requests.exceptions.HTTPError as e:
                raise ValueError(f"Langflow error: {e}") from e

    def _parse_response(self, response: dict) -> dict:
        """Ekstrak parsed output dari response Langflow."""
        try:
            outputs = response["outputs"][0]["outputs"][0]
            text = outputs["results"]["message"]["text"]
            parsed = json.loads(text)
            return parsed
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise ValueError(f"Gagal parse response Langflow: {e}\nRaw: {response}") from e

    def health_check(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            return r.status_code == 200
        except requests.exceptions.ConnectionError:
            return False