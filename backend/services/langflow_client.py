# backend/services/langflow_client.py
import requests
import time
from backend.config import LANGFLOW_BASE_URL, LANGFLOW_API_KEY


class LangflowClient:
    def __init__(self):
        self.base_url = LANGFLOW_BASE_URL
        self.headers = {}
        if LANGFLOW_API_KEY:
            self.headers["Authorization"] = f"Bearer {LANGFLOW_API_KEY}"

    def run_flow(
        self,
        flow_id: str,
        store_id: str,
        scenario: str = "S1_AMAN",
        max_retries: int = 3,
    ) -> dict:
        """
        Trigger Langflow flow via REST API.
        Retry otomatis jika gagal.
        """
        url = f"{self.base_url}/api/v1/run/{flow_id}"
        payload = {
            "input_value": store_id,
            "input_type": "text",
            "output_type": "text",
            "tweaks": {
                "DataFetcher-1": {
                    "store_id": store_id,
                    "scenario": scenario,
                }
            },
        }

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=120,  # Langflow bisa lambat saat pertama kali
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                if attempt == max_retries:
                    raise
                print(f"Langflow timeout (attempt {attempt}/{max_retries}), retry...")
                time.sleep(5 * attempt)

            except requests.exceptions.HTTPError as e:
                if response.status_code == 404:
                    raise ValueError(
                        f"Flow ID tidak ditemukan: {flow_id}\n"
                        f"Pastikan flow sudah diimport ke Langflow dan ID-nya benar."
                    ) from e
                raise

    def health_check(self) -> bool:
        """Cek apakah Langflow sedang berjalan."""
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            return r.status_code == 200
        except requests.exceptions.ConnectionError:
            return False