from __future__ import annotations

import json
import re
import secrets
from typing import Any


def json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or secrets.token_hex(4)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def first_tag(tags: list[list[str]], name: str) -> str | None:
    for tag in tags:
        if len(tag) > 1 and tag[0] == name:
            return tag[1]
    return None
