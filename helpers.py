from __future__ import annotations

import json
import re
import secrets
from typing import Any

MEDIA_URL_PREFIX = "/zapwall/api/v1/media/"


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


def media_url(media_id: str) -> str:
    return f"{MEDIA_URL_PREFIX}{media_id}"


def media_id_from_url(value: str | None) -> str | None:
    if not value:
        return None
    match = re.match(r"^/zapwall/api/v1/media/([^?/#]+)", value)
    if not match:
        return None
    return match.group(1)


def media_ids_from_urls(urls: list[str]) -> list[str]:
    return [media_id for url in urls if (media_id := media_id_from_url(url))]


def with_unlock_token(url: str, token: str) -> str:
    if not media_id_from_url(url):
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}token={token}"
