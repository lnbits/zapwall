from __future__ import annotations

from loguru import logger

from lnbits.core.services.nostr import send_nostr_dm
from lnbits.extensions.nostrclient.helpers import normalize_public_key
from lnbits.extensions.nostrclient.nostr.key import PrivateKey

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
    if settings.dm_mode.value == "manual":
        logger.info(
            "Zapwall DM delivery skipped for item {} because DM mode is manual.",
            item.id,
        )
        return DMDeliveryResponse(
            sent=False,
            event_id=None,
            event=None,
            message=message,
            relays=[],
        )

    sender_key = settings.bot_private_key or settings.signer_private_key
    if not sender_key:
        logger.warning(
            "Zapwall DM delivery skipped for item {} because no sender key is configured.",
            item.id,
        )
        return DMDeliveryResponse(
            sent=False,
            event_id=None,
            event=None,
            message=message,
            relays=[],
        )

    buyer_pubkey = normalize_public_key(buyer_pubkey)
    private_key = _load_private_key(sender_key)
    relays = settings.bot_relay_urls if settings.bot_private_key else settings.relay_urls
    relays = [relay for relay in relays if relay]
    sender_kind = "bot" if settings.bot_private_key else "creator"

    if not relays:
        logger.warning(
            "Zapwall DM delivery skipped for item {} because no relay URLs are configured.",
            item.id,
        )
        return DMDeliveryResponse(
            sent=False,
            event_id=None,
            event=None,
            message=message,
            relays=[],
        )

    logger.info(
        "Zapwall sending unlock DM for item {} to {} using {} key via {} relay(s).",
        item.id,
        buyer_pubkey,
        sender_kind,
        len(relays),
    )
    try:
        event = await send_nostr_dm(
            from_private_key_hex=private_key.hex(),
            to_pubkey_hex=buyer_pubkey,
            message=message,
            relays=relays,
        )
    except Exception as exc:
        logger.exception(
            "Zapwall DM delivery failed for item {} to {}: {}",
            item.id,
            buyer_pubkey,
            exc,
        )
        return DMDeliveryResponse(
            sent=False,
            event_id=None,
            event=None,
            message=message,
            relays=relays,
        )

    logger.info(
        "Zapwall DM delivery succeeded for item {} to {} with event {}.",
        item.id,
        buyer_pubkey,
        event.get("id"),
    )
    return DMDeliveryResponse(
        sent=True,
        event_id=event.get("id"),
        event=event,
        message=message,
        relays=relays,
    )
