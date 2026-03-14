from __future__ import annotations

from ..helpers import new_token


def create_unlock_token(item_id: str, buyer_pubkey: str) -> str:
    _ = (item_id, buyer_pubkey)
    return new_token()
