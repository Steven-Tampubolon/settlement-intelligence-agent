# backend/services/langflow_client.py
import json
import time
import requests
from backend.config import LANGFLOW_BASE_URL, LANGFLOW_API_KEY, LANGFLOW_FLOW_ID

# Node ID yang perlu di-tweak untuk retry
GROQ_NODE_ID = "GroqModel-30Czk"
DATA_FETCHER_NODE_ID = "DataFetcher-bG60r"

# System prompt eksplisit untuk retry
RETRY_SYSTEM_PROMPT = """Kamu adalah asisten keuangan untuk pemilik toko online Indonesia.

Tugasmu SATU: ubah data JSON yang diberikan menjadi pesan Telegram yang singkat, jelas, dan mudah dipahami pemilik toko yang sibuk.

ATURAN WAJIB:
1. JANGAN ubah angka sama sekali — tampilkan persis seperti di data
2. Format angka dengan titik sebagai pemisah ribuan (contoh: Rp 11.010.000)
3. Maksimal 8 baris pesan
4. Gunakan emoji secukupnya — jangan berlebihan
5. Selalu sertakan field action_button — satu aksi paling penting untuk user
6. Jika ada lebih dari satu settlement, WAJIB sebutkan net amount masing-masing secara individual — JANGAN dijumlah menjadi total saja
7. WAJIB sebutkan saldo kas saat ini (current_cash) di full_message
8. PERHATIAN: Sebutkan SETIAP angka penting secara eksplisit di full_message

Output HARUS berupa JSON valid dengan struktur ini:
- status_line: string, baris pertama, status + emoji
- incoming_funds: string, ringkasan uang yang akan masuk
- key_decision: string, satu keputusan paling penting
- full_message: string, pesan lengkap siap kirim ke Telegram
- action_button: string, teks tombol aksi maksimal 4 kata

Jangan tambahkan penjelasan di luar JSON."""


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
        Jalankan flow dengan retry logic:
        - Attempt 1: prompt normal
        - Attempt 2: retry dengan system prompt lebih eksplisit
        - Attempt 3: retry kedua dengan system prompt eksplisit
        - Jika semua gagal: return fallback template
        """
        last_result = None

        for attempt in range(1, max_retries + 1):
            try:
                use_explicit_prompt = attempt > 1
                result = self._run_single(
                    store_id=store_id,
                    scenario=scenario,
                    use_explicit_prompt=use_explicit_prompt,
                )

                # Cek apakah valid
                if result.get("valid"):
                    if attempt > 1:
                        print(f"    ✅ Valid setelah retry ke-{attempt - 1}")
                    return result

                # Tidak valid — log dan retry
                last_result = result
                missing = result.get("missing_numbers", [])
                reason = result.get("reason", "unknown")
                print(f"    ⚠️  Attempt {attempt}/{max_retries} invalid — reason: {reason}, missing: {missing}")

                if attempt < max_retries:
                    time.sleep(2)  # Tunggu sebentar sebelum retry

            except requests.exceptions.Timeout:
                print(f"    ⏱️  Attempt {attempt}/{max_retries} timeout")
                if attempt == max_retries:
                    raise
                time.sleep(5 * attempt)

            except requests.exceptions.HTTPError as e:
                raise ValueError(f"Langflow error: {e}") from e

        # Semua attempt gagal — gunakan fallback template
        print(f"    🔄 Semua {max_retries} attempt gagal — gunakan fallback template")
        return self._build_fallback(last_result)

    def _run_single(
        self,
        store_id: str,
        scenario: str,
        use_explicit_prompt: bool = False,
    ) -> dict:
        """Jalankan satu kali call ke Langflow."""
        url = f"{self.base_url}/api/v1/run/{self.flow_id}"

        tweaks = {
            DATA_FETCHER_NODE_ID: {
                "store_id": store_id,
                "scenario": scenario,
            }
        }

        # Pada retry, override system prompt Groq dengan versi lebih eksplisit
        if use_explicit_prompt:
            tweaks[GROQ_NODE_ID] = {
                "system_message": RETRY_SYSTEM_PROMPT,
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
        return self._parse_response(response.json())

    def _parse_response(self, response: dict) -> dict:
        """Ekstrak parsed output dari response Langflow."""
        try:
            outputs = response["outputs"][0]["outputs"][0]
            text = outputs["results"]["message"]["text"]
            return json.loads(text)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise ValueError(
                f"Gagal parse response Langflow: {e}\nRaw: {response}"
            ) from e

    def _build_fallback(self, last_result: dict | None) -> dict:
        """
        Bangun fallback response ketika semua retry gagal.
        Return struktur yang sama dengan output valid agar alert_service
        bisa handle dengan satu code path.
        """
        if last_result and last_result.get("parsed"):
            # Pakai parsed output LLM meski tidak valid — lebih baik dari kosong
            parsed = last_result["parsed"]
        else:
            parsed = None

        return {
            "valid": False,
            "parsed": parsed,
            "reason": "max_retries_exceeded",
            "missing_numbers": last_result.get("missing_numbers", []) if last_result else [],
            "_fallback_used": True,
        }

    def health_check(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=5)
            return r.status_code == 200
        except requests.exceptions.ConnectionError:
            return False