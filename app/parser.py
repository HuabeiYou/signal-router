import re
from typing import Any


def _walk_payload(value: Any, path: str, fields: dict[str, Any], text_chunks: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            _walk_payload(child, child_path, fields, text_chunks)
        return

    if isinstance(value, list):
        for idx, child in enumerate(value):
            child_path = f"{path}[{idx}]"
            _walk_payload(child, child_path, fields, text_chunks)
        return

    if isinstance(value, (str, int, float, bool)):
        # Keep full dotted-path value for nested field matching if needed.
        if path:
            fields[path] = value
            # Keep leaf key for simple matching, e.g. "symbol", "title".
            leaf_key = path.split(".")[-1].split("[")[0]
            fields.setdefault(leaf_key, value)
        if isinstance(value, str) and value.strip():
            text_chunks.append(value)


def parse_signal_fields(payload: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    text_chunks: list[str] = []

    _walk_payload(payload, "", fields, text_chunks)

    content_text = ""
    if isinstance(payload.get("text"), dict):
        content_text = str(payload["text"].get("content", ""))
    elif isinstance(payload.get("markdown"), dict):
        content_text = str(payload["markdown"].get("content", ""))

    if content_text:
        text_chunks.insert(0, content_text)

    message_text = "\n".join(chunk for chunk in text_chunks if chunk).strip()
    if message_text:
        fields["message_text"] = message_text
        kv_pattern = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+?)\s*$")
        for line in message_text.splitlines():
            match = kv_pattern.match(line)
            if match:
                k, v = match.groups()
                fields[k] = v

    return fields
