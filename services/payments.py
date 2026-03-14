from __future__ import annotations

from lnbits.core.crud import get_standalone_payment
from lnbits.extensions.nostrclient.helpers import normalize_public_key
from lnbits.helpers import urlsafe_short_hash

from ..crud import (
    create_purchase,
    get_purchase_by_payment_hash,
    get_purchase_by_zap_event,
    get_purchase_for_item_pubkey,
    get_settings,
    update_purchase,
)
from ..models import ZapwallItem, ZapwallPurchase, timestamp_now
from .dms import send_unlock_dm
from .receipts import ensure_receipt_for_purchase
from .unlocks import create_unlock_token


async def get_payment_status(item: ZapwallItem, payment_hash: str) -> bool:
    payment = await get_standalone_payment(payment_hash, incoming=True)
    if not payment:
        return False
    if payment.extra.get("tag") != "zapwall" or payment.extra.get("item_id") != item.id:
        return False
    return bool(payment.success)


async def create_access_purchase(
    item: ZapwallItem,
    buyer_pubkey: str,
    amount_paid: int,
    *,
    buyer_npub: str | None = None,
    zap_event_id: str | None = None,
    payment_hash: str | None = None,
    base_url: str | None = None,
) -> tuple[ZapwallPurchase, str]:
    buyer_pubkey = normalize_public_key(buyer_pubkey)
    if payment_hash:
        existing = await get_purchase_by_payment_hash(payment_hash)
        if existing:
            return existing, existing.unlock_token
    if zap_event_id:
        existing = await get_purchase_by_zap_event(zap_event_id)
        if existing:
            return existing, existing.unlock_token
    existing_access = await get_purchase_for_item_pubkey(item.id, buyer_pubkey)
    if existing_access:
        return existing_access, existing_access.unlock_token

    token = create_unlock_token(item.id, buyer_pubkey)
    purchase = ZapwallPurchase(
        id=urlsafe_short_hash(),
        item_id=item.id,
        creator_id=item.creator_id,
        buyer_pubkey=buyer_pubkey,
        buyer_npub=buyer_npub,
        zap_event_id=zap_event_id,
        payment_hash=payment_hash,
        amount_paid=amount_paid,
        unlock_token=token,
    )
    purchase = await create_purchase(purchase)
    receipt = await ensure_receipt_for_purchase(purchase)
    settings = await get_settings(item.wallet)
    if (
        item.auto_dm_unlock
        and settings
        and base_url
        and (settings.bot_private_key or settings.dm_mode.value == "manual")
    ):
        dm_result = await send_unlock_dm(
            settings=settings,
            item=item,
            buyer_pubkey=buyer_pubkey,
            token=token,
            receipt=receipt,
            base_url=base_url,
        )
        if dm_result.sent:
            purchase.unlock_sent = True
            purchase.unlock_sent_at = timestamp_now()
            await update_purchase(purchase)
    return purchase, token


async def finalize_invoice_payment(
    item: ZapwallItem, payment_hash: str
) -> ZapwallPurchase | None:
    existing = await get_purchase_by_payment_hash(payment_hash)
    if existing:
        return existing
    payment = await get_standalone_payment(payment_hash, incoming=True)
    if not payment or not payment.success:
        return None
    if payment.extra.get("tag") != "zapwall" or payment.extra.get("item_id") != item.id:
        return None
    buyer_pubkey = payment.extra.get("buyer_pubkey")
    if not buyer_pubkey:
        return None
    purchase, _ = await create_access_purchase(
        item=item,
        buyer_pubkey=buyer_pubkey,
        amount_paid=payment.amount,
        buyer_npub=payment.extra.get("buyer_npub"),
        payment_hash=payment_hash,
        base_url=payment.extra.get("base_url"),
    )
    return purchase
