import asyncio
import json

from bolt11 import decode as bolt11_decode
from loguru import logger

from lnbits.extensions.nostrclient.crud import get_relays
from lnbits.extensions.nostrclient.nostr.client.client import NostrClient
from lnbits.extensions.nostrclient.nostr.event import Event
from lnbits.helpers import urlsafe_short_hash
from lnbits.settings import settings

from .crud import (
    create_nostr_event,
    get_item_by_preview_event_id,
    get_published_items_with_previews,
)
from .helpers import first_tag, json_dumps
from .models import ZapwallNostrEvent
from .services.nostr import get_npub
from .services.payments import create_access_purchase

LISTENER_PREFIX = "zapwall-listener"
_active_subscriptions: set[str] = set()
_relay_urls: set[str] = set()
listener_client = NostrClient()


def _subscription_id(item_id: str) -> str:
    return f"{LISTENER_PREFIX}:{item_id}"


async def _sync_subscriptions():
    global _relay_urls
    relay_urls = {relay.url for relay in await get_relays() if relay.url}
    if relay_urls != _relay_urls:
        listener_client.reconnect(list(relay_urls))
        _active_subscriptions.clear()
        _relay_urls = relay_urls
    items = await get_published_items_with_previews()
    for item in items:
        if not item.preview_event_id:
            continue
        sub_id = _subscription_id(item.id)
        if sub_id in _active_subscriptions:
            continue
        listener_client.relay_manager.add_subscription(
            sub_id, [{"kinds": [9735], "#e": [item.preview_event_id]}]
        )
        _active_subscriptions.add(sub_id)


def _parse_buyer_pubkey(event_json: dict) -> tuple[str | None, str | None]:
    description = first_tag(event_json.get("tags", []), "description")
    if not description:
        return event_json.get("pubkey"), get_npub(event_json.get("pubkey"))
    try:
        zap_request = json.loads(description)
    except json.JSONDecodeError:
        return event_json.get("pubkey"), get_npub(event_json.get("pubkey"))
    buyer_pubkey = zap_request.get("pubkey") or event_json.get("pubkey")
    return buyer_pubkey, get_npub(buyer_pubkey)


def _parse_amount(tags: list[list[str]]) -> tuple[int | None, str | None]:
    amount_tag = first_tag(tags, "amount")
    if amount_tag:
        try:
            return int(int(amount_tag) / 1000), None
        except ValueError:
            pass
    bolt11 = first_tag(tags, "bolt11")
    if not bolt11:
        return None, None
    try:
        invoice = bolt11_decode(bolt11)
        amount_msat = getattr(invoice, "amount_msat", None)
        amount_sat = int(amount_msat / 1000) if amount_msat else None
        return amount_sat, getattr(invoice, "payment_hash", None)
    except Exception:
        return None, None


async def _handle_event_message(event_message):
    if not event_message.subscription_id.startswith(f"{LISTENER_PREFIX}:"):
        return
    event_json = json.loads(event_message.event)
    event = Event(
        content=event_json.get("content", ""),
        public_key=event_json.get("pubkey"),
        created_at=event_json.get("created_at"),
        kind=event_json.get("kind", 1),
        tags=event_json.get("tags", []),
        signature=event_json.get("sig"),
    )
    try:
        verified = event.verify()
    except Exception:
        verified = False
    preview_event_id = first_tag(event_json.get("tags", []), "e")
    item = await get_item_by_preview_event_id(preview_event_id or "")
    await create_nostr_event(
        ZapwallNostrEvent(
            id=urlsafe_short_hash(),
            item_id=item.id if item else None,
            event_id=event_json.get("id", event_message.event_id),
            kind=event_json.get("kind", 1),
            pubkey=event_json.get("pubkey", ""),
            raw_event=json_dumps(event_json),
            verified=verified,
        )
    )
    if not item or not verified:
        return

    amount_sat, payment_hash = _parse_amount(event_json.get("tags", []))
    if not amount_sat:
        return
    buyer_pubkey, buyer_npub = _parse_buyer_pubkey(event_json)
    if not buyer_pubkey:
        return
    if item.exact_amount_only and amount_sat != item.price:
        return
    if amount_sat < item.price:
        return
    await create_access_purchase(
        item=item,
        buyer_pubkey=buyer_pubkey,
        buyer_npub=buyer_npub,
        amount_paid=amount_sat,
        zap_event_id=event_json.get("id", event_message.event_id),
        payment_hash=payment_hash,
        base_url=settings.lnbits_baseurl,
    )


async def run_zapwall_listener():
    while True:
        try:
            await _sync_subscriptions()
            while listener_client.relay_manager.message_pool.has_events():
                event_message = listener_client.relay_manager.message_pool.get_event()
                await _handle_event_message(event_message)
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            listener_client.close()
            raise
        except Exception as exc:
            logger.warning(f"[zapwall] listener loop failed: {exc}")
            await asyncio.sleep(5)
