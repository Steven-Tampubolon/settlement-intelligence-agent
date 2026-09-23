# langflow/schema/message.py
class Message:
    def __init__(self, text="", **kwargs):
        self.text = text

    def __repr__(self):
        return f"Message({self.text[:50]}...)"