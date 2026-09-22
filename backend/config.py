# backend/config.py
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
LANGFLOW_BASE_URL = os.environ.get("LANGFLOW_BASE_URL", "http://localhost:7860")
LANGFLOW_API_KEY = os.environ.get("LANGFLOW_API_KEY", "")
LANGFLOW_FLOW_ID = os.environ.get("LANGFLOW_FLOW_ID", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./settlement_agent.db")

# Validasi saat startup
def validate_config():
    missing = []
    for name, val in [
        ("GROQ_API_KEY", GROQ_API_KEY),
        ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
        ("LANGFLOW_FLOW_ID", LANGFLOW_FLOW_ID),
    ]:
        if not val:
            missing.append(name)
    if missing:
        raise EnvironmentError(
            f"Environment variable wajib tidak ada: {', '.join(missing)}\n"
            f"Salin .env.example ke .env dan isi nilainya."
        )