from __future__ import annotations

from lnbits.extensions.nostrclient.helpers import normalize_public_key
from lnbits.extensions.nostrclient.nostr.event import EncryptedDirectMessage
from lnbits.extensions.nostrclient.nostr.key import PrivateKey
from lnbits.extensions.nostrclient.router import nostr_client

from ..models import DMDeliveryResponse, ZapwallItem, ZapwallReceipt, ZapwallSettings


def _load_private_key(raw: str) -> PrivateKey:
    if raw.startswith("nsec1"):
        return PrivateKey.from_nsec(raw)
    return PrivateKey(bytes.fromhex(raw))


async def send_unlock_dm(
    settings: ZapwallSettings,
    item: ZapwallItem,
    buyer_pubkey: str,
    token: str,
    receipt: ZapwallReceipt,
    base_url: str,
) -> DMDeliveryResponse:
    message = (
        f"You unlocked: {item.title}\n\n"
        f"Open:\n{base_url}zapwall/unlock/{token}\n\n"
        f"Receipt:\n{receipt.receipt_signature}"
    )
    if not settings.bot_private_key:
        return DMDeliveryResponse(
            sent=False,
            event_id=None,
            event=None,
            message=message,
            relays=settings.bot_relay_urls,
        )
    buyer_pubkey = normalize_public_key(buyer_pubkey)
    private_key = _load_private_key(settings.bot_private_key)
    dm = EncryptedDirectMessage(
        recipient_pubkey=buyer_pubkey, cleartext_content=message
    )
    private_key.sign_event(dm)
    event = {
        "id": dm.id,
        "pubkey": dm.public_key,
        "created_at": dm.created_at,
        "kind": dm.kind,
        "tags": dm.tags,
        "content": dm.content,
        "sig": dm.signature,
    }
    nostr_client.relay_manager.publish_message(dm.to_message())
    return DMDeliveryResponse(
        sent=True,
        event_id=dm.id,
        event=event,
        message=message,
        relays=settings.bot_relay_urls,
    )
