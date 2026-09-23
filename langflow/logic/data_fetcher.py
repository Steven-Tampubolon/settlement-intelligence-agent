import json
from pathlib import Path


def fetch_store_data(store_id: str, scenario: str = "S1_AMAN") -> dict:
    mock_data_path = (
        Path(__file__).parent.parent / "mock_data" / "store_scenarios.json"
    )
    with open(mock_data_path, "r", encoding="utf-8") as f:
        all_scenarios = json.load(f)
    if scenario not in all_scenarios["scenarios"]:
        raise ValueError(f"Scenario '{scenario}' tidak ditemukan.")
    data = all_scenarios["scenarios"][scenario]["data"].copy()
    data["store_id"] = store_id
    return data