import json
from pathlib import Path

from lfx.custom.custom_component.component import Component
from lfx.io import Output, StrInput
from lfx.schema.data import Data


class DataFetcher(Component):
    display_name = "Data Fetcher"
    description = "Mengambil data settlement dari mock data (swap ke real API nanti)"

    inputs = [
        StrInput(name="store_id", display_name="Store ID", required=True, value="toko_andi_001"),
        StrInput(name="scenario", display_name="Scenario (Mock)", value="S1_AMAN", required=False),
    ]

    outputs = [
        Output(display_name="Raw Store Data", name="raw_data", method="fetch_data"),
    ]

    def fetch_data(self) -> Data:
        mock_data_path = Path("/app/langflow/custom_components/mock_data/store_scenarios.json")
        with open(mock_data_path, "r", encoding="utf-8") as f:
            all_scenarios = json.load(f)
        if self.scenario not in all_scenarios["scenarios"]:
            raise ValueError(f"Scenario '{self.scenario}' tidak ditemukan.")
        result = all_scenarios["scenarios"][self.scenario]["data"].copy()
        result["store_id"] = self.store_id
        self.status = result
        return Data(data=result)

    def build(self):
        return self.fetch_data