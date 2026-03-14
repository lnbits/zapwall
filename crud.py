from __future__ import annotations

import json

from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import (
    DashboardStats,
    ZapwallCreator,
    ZapwallItem,
    ZapwallNostrEvent,
    ZapwallPurchase,
    ZapwallReceipt,
    ZapwallSettings,
    timestamp_now,
)

db = Database("ext_zapwall")


async def get_creator_by_wallet(wallet: str) -> ZapwallCreator | None:
    return await db.fetchone(
        "SELECT * FROM zapwall.creators WHERE wallet = :wallet",
        {"wallet": wallet},
        ZapwallCreator,
    )


async def create_creator(creator: ZapwallCreator) -> ZapwallCreator:
    await db.insert("zapwall.creators", creator)
    return creator


async def update_creator(creator: ZapwallCreator) -> ZapwallCreator:
    creator.updated_at = timestamp_now()
    await db.update("zapwall.creators", creator)
    return creator


async def get_settings(wallet: str) -> ZapwallSettings | None:
    return await db.fetchone(
        "SELECT * FROM zapwall.settings WHERE wallet = :wallet",
        {"wallet": wallet},
        ZapwallSettings,
    )


async def create_settings(settings: ZapwallSettings) -> ZapwallSettings:
    await db.insert("zapwall.settings", settings)
    return settings


async def update_settings(settings: ZapwallSettings) -> ZapwallSettings:
    settings.updated_at = timestamp_now()
    await db.update("zapwall.settings", settings)
    return settings


async def get_or_create_settings(wallet: str, user_id: str) -> ZapwallSettings:
    existing = await get_settings(wallet)
    if existing:
        return existing
    settings = ZapwallSettings(id=urlsafe_short_hash(), wallet=wallet, user_id=user_id)
    return await create_settings(settings)


async def get_item(item_id: str) -> ZapwallItem | None:
    return await db.fetchone(
        "SELECT * FROM zapwall.items WHERE id = :id", {"id": item_id}, ZapwallItem
    )


async def get_item_by_slug(wallet: str, slug: str) -> ZapwallItem | None:
    return await db.fetchone(
        "SELECT * FROM zapwall.items WHERE wallet = :wallet AND slug = :slug",
        {"wallet": wallet, "slug": slug},
        ZapwallItem,
    )


async def get_item_by_preview_event_id(preview_event_id: str) -> ZapwallItem | None:
    return await db.fetchone(
        "SELECT * FROM zapwall.items WHERE preview_event_id = :preview_event_id",
        {"preview_event_id": preview_event_id},
        ZapwallItem,
    )


async def create_item(item: ZapwallItem) -> ZapwallItem:
    await db.insert("zapwall.items", item)
    return item


async def update_item(item: ZapwallItem) -> ZapwallItem:
    item.updated_at = timestamp_now()
    await db.update("zapwall.items", item)
    return item


async def delete_item(item_id: str) -> None:
    await db.execute("DELETE FROM zapwall.items WHERE id = :id", {"id": item_id})


async def get_items(wallet_ids: list[str]) -> list[ZapwallItem]:
    if not wallet_ids:
        return []
    placeholders = ",".join([f":wallet_{i}" for i in range(len(wallet_ids))])
    values = {f"wallet_{i}": wallet_id for i, wallet_id in enumerate(wallet_ids)}
    return await db.fetchall(
        f"""
        SELECT * FROM zapwall.items
        WHERE wallet IN ({placeholders})
        ORDER BY created_at DESC
        """,
        values,
        ZapwallItem,
    )


async def get_wallet_items(wallet: str) -> list[ZapwallItem]:
    return await db.fetchall(
        """
        SELECT * FROM zapwall.items
        WHERE wallet = :wallet
        ORDER BY created_at DESC
        """,
        {"wallet": wallet},
        ZapwallItem,
    )


async def get_published_items_with_previews() -> list[ZapwallItem]:
    return await db.fetchall(
        """
        SELECT * FROM zapwall.items
        WHERE status = 'published' AND preview_event_id IS NOT NULL
        ORDER BY updated_at DESC
        """,
        model=ZapwallItem,
    )


async def create_purchase(purchase: ZapwallPurchase) -> ZapwallPurchase:
    await db.insert("zapwall.purchases", purchase)
    return purchase


async def update_purchase(purchase: ZapwallPurchase) -> ZapwallPurchase:
    await db.update("zapwall.purchases", purchase)
    return purchase


async def get_purchase(purchase_id: str) -> ZapwallPurchase | None:
    return await db.fetchone(
        "SELECT * FROM zapwall.purchases WHERE id = :id",
        {"id": purchase_id},
        ZapwallPurchase,
    )


async def get_purchase_by_unlock_token(unlock_token: str) -> ZapwallPurchase | None:
    return await db.fetchone(
        "SELECT * FROM zapwall.purchases WHERE unlock_token = :unlock_token",
        {"unlock_token": unlock_token},
        ZapwallPurchase,
    )


async def get_purchase_by_payment_hash(payment_hash: str) -> ZapwallPurchase | None:
    return await db.fetchone(
        "SELECT * FROM zapwall.purchases WHERE payment_hash = :payment_hash",
        {"payment_hash": payment_hash},
        ZapwallPurchase,
    )


async def get_purchase_by_zap_event(zap_event_id: str) -> ZapwallPurchase | None:
    return await db.fetchone(
        "SELECT * FROM zapwall.purchases WHERE zap_event_id = :zap_event_id",
        {"zap_event_id": zap_event_id},
        ZapwallPurchase,
    )


async def get_purchase_for_item_pubkey(
    item_id: str, buyer_pubkey: str
) -> ZapwallPurchase | None:
    return await db.fetchone(
        """
        SELECT * FROM zapwall.purchases
        WHERE item_id = :item_id AND buyer_pubkey = :buyer_pubkey
        ORDER BY created_at DESC
        LIMIT 1
        """,
        {"item_id": item_id, "buyer_pubkey": buyer_pubkey},
        ZapwallPurchase,
    )


async def get_item_purchases(item_id: str) -> list[ZapwallPurchase]:
    return await db.fetchall(
        """
        SELECT * FROM zapwall.purchases
        WHERE item_id = :item_id
        ORDER BY created_at DESC
        """,
        {"item_id": item_id},
        ZapwallPurchase,
    )


async def get_recent_unlocks(wallet: str, limit: int = 10) -> list[dict]:
    rows = await db.fetchall(
        """
        SELECT p.id, p.item_id, p.buyer_pubkey, p.amount_paid, p.unlock_sent, p.created_at,
               i.title
        FROM zapwall.purchases p
        JOIN zapwall.items i ON i.id = p.item_id
        WHERE i.wallet = :wallet
        ORDER BY p.created_at DESC
        LIMIT :limit
        """,
        {"wallet": wallet, "limit": limit},
    )
    return [dict(row) for row in rows]


async def create_receipt(receipt: ZapwallReceipt) -> ZapwallReceipt:
    await db.insert("zapwall.receipts", receipt)
    return receipt


async def get_latest_receipt_for_purchase(purchase_id: str) -> ZapwallReceipt | None:
    return await db.fetchone(
        """
        SELECT * FROM zapwall.receipts
        WHERE purchase_id = :purchase_id
        ORDER BY created_at DESC
        LIMIT 1
        """,
        {"purchase_id": purchase_id},
        ZapwallReceipt,
    )


async def create_nostr_event(event: ZapwallNostrEvent) -> ZapwallNostrEvent:
    await db.insert("zapwall.nostr_events", event)
    return event


async def get_dashboard_stats(wallet: str) -> DashboardStats:
    item_row = await db.fetchone(
        "SELECT COUNT(*) AS count FROM zapwall.items WHERE wallet = :wallet",
        {"wallet": wallet},
    )
    sales_row = await db.fetchone(
        """
        SELECT COUNT(*) AS sales_count, COALESCE(SUM(p.amount_paid), 0) AS sats_earned
        FROM zapwall.purchases p
        JOIN zapwall.items i ON i.id = p.item_id
        WHERE i.wallet = :wallet
        """,
        {"wallet": wallet},
    )
    recent_unlocks = await get_recent_unlocks(wallet)
    item_row_dict = dict(item_row) if item_row else {}
    sales_row_dict = dict(sales_row) if sales_row else {}
    item_count = item_row_dict.get("count", 0)
    sales_count = sales_row_dict.get("sales_count", 0)
    sats_earned = sales_row_dict.get("sats_earned", 0)
    return DashboardStats(
        items=item_count or 0,
        sales_count=sales_count or 0,
        sats_earned=sats_earned or 0,
        recent_unlocks=recent_unlocks,
    )


async def get_or_create_creator(wallet: str, display_name: str | None = None):
    creator = await get_creator_by_wallet(wallet)
    if creator:
        return creator
    creator = ZapwallCreator(
        id=urlsafe_short_hash(),
        wallet=wallet,
        display_name=display_name,
    )
    return await create_creator(creator)
