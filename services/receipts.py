from __future__ import annotations

import hashlib
import hmac

from lnbits.helpers import urlsafe_short_hash
from lnbits.settings import settings as lnbits_settings

from ..crud import create_receipt, get_item, get_latest_receipt_for_purchase, get_settings
from ..helpers import json_dumps
from ..models import ZapwallPurchase, ZapwallReceipt


def _sign_payload(payload: str) -> str:
    return hmac.new(
        lnbits_settings.auth_secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


async def ensure_receipt_for_purchase(purchase: ZapwallPurchase) -> ZapwallReceipt:
    existing = await get_latest_receipt_for_purchase(purchase.id)
    if existing:
        return existing
    item = await get_item(purchase.item_id)
    assert item, "Missing item for purchase receipt."
    settings = await get_settings(item.wallet)
    payload = json_dumps(
        {
            "kind": "zapwall_receipt",
            "item_id": item.id,
            "creator_pubkey": settings.creator_nostr_pubkey if settings else None,
            "buyer_pubkey": purchase.buyer_pubkey,
            "amount": purchase.amount_paid,
            "currency": "sats",
            "purchased_at": purchase.created_at,
            "expires_at": item.expires_at,
        }
    )
    receipt = ZapwallReceipt(
        id=urlsafe_short_hash(),
        purchase_id=purchase.id,
        item_id=item.id,
        buyer_pubkey=purchase.buyer_pubkey,
        receipt_payload=payload,
        receipt_signature=_sign_payload(payload),
        expires_at=item.expires_at,
    )
    return await create_receipt(receipt)
