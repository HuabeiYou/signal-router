import re
from typing import Any


def parse_signal_fields(payload: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}

    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)):
            fields[key] = value

    text = ""
    if isinstance(payload.get("text"), dict):
        text = str(payload["text"].get("content", ""))
    elif isinstance(payload.get("markdown"), dict):
        text = str(payload["markdown"].get("content", ""))

    if text:
        fields["message_text"] = text
        kv_pattern = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+?)\s*$")
        for line in text.splitlines():
            match = kv_pattern.match(line)
            if match:
                k, v = match.groups()
                fields[k] = v

    return fields
