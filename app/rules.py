from typing import Any


def match_rule(parsed_fields: dict[str, Any], conditions: dict[str, Any]) -> bool:
    op = conditions.get("op", "and")
    items = conditions.get("items", [])
    if op != "and":
        return False
    message_text = str(parsed_fields.get("message_text", ""))
    message_text_lower = message_text.lower()
    for item in items:
        item_type = item.get("type")
        if item_type == "always":
            continue
        if item_type == "contains_field":
            field = item.get("field")
            if not field or field not in parsed_fields:
                return False
        elif item_type == "contains_text":
            target_text = str(item.get("text", "")).strip()
            if not target_text:
                return False
            if target_text.lower() not in message_text_lower:
                return False
        else:
            return False
    return True
