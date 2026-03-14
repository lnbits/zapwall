from __future__ import annotations

from lnbits.extensions.nostrclient.helpers import normalize_public_key
from lnbits.extensions.nostrclient.nostr.event import Event
from lnbits.extensions.nostrclient.nostr.key import PrivateKey, PublicKey
from lnbits.extensions.nostrclient.router import nostr_client

from ..crud import create_nostr_event
from ..helpers import json_dumps
from ..models import ZapwallCreator, ZapwallItem, ZapwallNostrEvent, ZapwallSettings
from lnbits.helpers import urlsafe_short_hash


def _load_private_key(raw: str) -> PrivateKey:
    if raw.startswith("nsec1"):
        return PrivateKey.from_nsec(raw)
    return PrivateKey(bytes.fromhex(raw))


async def build_preview_event(
    item: ZapwallItem,
    settings: ZapwallSettings,
    creator: ZapwallCreator,
    override_content: str | None = None,
) -> dict:
    creator_pubkey = settings.creator_nostr_pubkey or creator.nostr_pubkey
    if not creator_pubkey:
        raise ValueError("Creator nostr pubkey is not configured.")
    creator_pubkey = normalize_public_key(creator_pubkey)
    content = override_content or (
        f"{item.preview_text}\n\n⚡ Zap {item.price} sats to unlock full content."
    )
    tags = [
        ["t", "zapwall"],
        ["zapwall", f"item_id:{item.id}"],
        ["price", str(item.price)],
        ["unit", "sats"],
        ["lnbits", f"/zapwall/api/v1/items/{item.id}"],
        ["alt", f"Preview for {item.title}"],
    ]
    event = Event(content=content, public_key=creator_pubkey, tags=tags)
    return {
        "id": event.id,
        "pubkey": event.public_key,
        "created_at": event.created_at,
        "kind": event.kind,
        "tags": event.tags,
        "content": event.content,
        "sig": event.signature,
    }


async def publish_preview_event(event_dict: dict, private_key_raw: str) -> dict:
    private_key = _load_private_key(private_key_raw)
    event = Event(
        content=event_dict["content"],
        public_key=event_dict["pubkey"],
        created_at=event_dict["created_at"],
        kind=event_dict["kind"],
        tags=event_dict["tags"],
    )
    private_key.sign_event(event)
    event_payload = {
        "id": event.id,
        "pubkey": event.public_key,
        "created_at": event.created_at,
        "kind": event.kind,
        "tags": event.tags,
        "content": event.content,
        "sig": event.signature,
    }
    nostr_client.relay_manager.publish_message(event.to_message())
    await create_nostr_event(
        ZapwallNostrEvent(
            id=urlsafe_short_hash(),
            item_id=None,
            event_id=event.id,
            kind=event.kind,
            pubkey=event.public_key or "",
            raw_event=json_dumps(event_payload),
            verified=True,
        )
    )
    return event_payload


def get_npub(pubkey_hex: str | None) -> str | None:
    if not pubkey_hex:
        return None
    return PublicKey(bytes.fromhex(normalize_public_key(pubkey_hex))).bech32()
