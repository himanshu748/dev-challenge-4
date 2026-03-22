from __future__ import annotations

import json


def extract_json_payload(raw_text: str):
    text = raw_text.strip()
    candidates = [text]

    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            candidates.append("\n".join(lines[1:-1]).strip())

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    for start_index, char in enumerate(text):
        if char not in "{[":
            continue

        depth = 0
        in_string = False
        escape = False

        for index in range(start_index, len(text)):
            current = text[index]

            if in_string:
                if escape:
                    escape = False
                elif current == "\\":
                    escape = True
                elif current == '"':
                    in_string = False
                continue

            if current == '"':
                in_string = True
            elif current in "{[":
                depth += 1
            elif current in "}]":
                depth -= 1
                if depth == 0:
                    candidate = text[start_index : index + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    raise ValueError("AI did not return valid JSON.")


def compact_json(value, max_chars: int = 12000) -> str:
    rendered = json.dumps(value, ensure_ascii=False, indent=2)
    if len(rendered) <= max_chars:
        return rendered
    return f"{rendered[:max_chars]}\n...<truncated>"
