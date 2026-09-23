# langflow/schema/data.py
class Data:
    def __init__(self, data=None, **kwargs):
        self.data = data or {}

    def __repr__(self):
        return f"Data({self.data})"