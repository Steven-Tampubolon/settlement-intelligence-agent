# langflow/custom.py
class CustomComponent:
    display_name: str = ""
    description: str = ""

    def build_config(self) -> dict:
        return {}

    def build(self, *args, **kwargs):
        raise NotImplementedError

# Alias yang dipakai Langflow 1.10.2
Component = CustomComponent