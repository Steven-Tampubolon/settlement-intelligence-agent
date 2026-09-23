# langflow/io.py
# Stub untuk lfx.io — digunakan saat testing lokal tanpa Langflow

class _BaseInput:
    def __init__(self, name="", display_name="", required=False, value=None, **kwargs):
        self.name = name
        self.display_name = display_name
        self.required = required
        self.value = value

StrInput = _BaseInput
DataInput = _BaseInput
MessageInput = _BaseInput
SecretStrInput = _BaseInput
IntInput = _BaseInput
BoolInput = _BaseInput
MultilineInput = _BaseInput
DropdownInput = _BaseInput
SliderInput = _BaseInput

class Output:
    def __init__(self, display_name="", name="", method="", **kwargs):
        self.display_name = display_name
        self.name = name
        self.method = method