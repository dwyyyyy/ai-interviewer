from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


def extract_json(text: str, fallback: Any) -> Any:
    if not text:
        return deepcopy(fallback)
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", cleaned, flags=re.S)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return deepcopy(fallback)
    return deepcopy(fallback)
