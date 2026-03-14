from lnbits.db import Database


DEFAULT_RELAYS_JSON = (
    '["wss://relay.damus.io","wss://relay.primal.net",'
    '"wss://nos.lol","wss://relay.nostr.band","wss://offchain.pub"]'
)


async def m001_initial(db: Database):
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS zapwall.creators (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL UNIQUE,
            nostr_pubkey TEXT,
            nostr_npub TEXT,
            display_name TEXT,
            profile_json TEXT DEFAULT '{}',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        """
    )
    await db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS zapwall.items (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            creator_id TEXT NOT NULL,
            slug TEXT NOT NULL,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            preview_text TEXT NOT NULL DEFAULT '',
            full_text TEXT NOT NULL DEFAULT '',
            price INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'sats',
            status TEXT NOT NULL DEFAULT 'draft',
            preview_event_id TEXT,
            preview_event_raw TEXT,
            cover_image TEXT,
            preview_media_urls_json TEXT DEFAULT '[]',
            media_urls_json TEXT DEFAULT '[]',
            unlock_type TEXT NOT NULL DEFAULT 'dm_link',
            exact_amount_only BOOLEAN NOT NULL DEFAULT false,
            auto_dm_unlock BOOLEAN NOT NULL DEFAULT true,
            expires_at INTEGER,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        """
    )
    await db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS zapwall.zapwall_item_wallet_slug_idx
        ON items (wallet, slug);
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS zapwall.purchases (
            id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL,
            creator_id TEXT NOT NULL,
            buyer_pubkey TEXT NOT NULL,
            buyer_npub TEXT,
            zap_event_id TEXT,
            payment_hash TEXT,
            amount_paid INTEGER NOT NULL,
            unlock_token TEXT NOT NULL,
            unlock_sent BOOLEAN NOT NULL DEFAULT false,
            unlock_sent_at INTEGER,
            created_at INTEGER NOT NULL
        );
        """
    )
    await db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS zapwall.zapwall_purchase_item_pubkey_idx
        ON purchases (item_id, buyer_pubkey);
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS zapwall.receipts (
            id TEXT PRIMARY KEY,
            purchase_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            buyer_pubkey TEXT NOT NULL,
            receipt_payload TEXT NOT NULL,
            receipt_signature TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER
        );
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS zapwall.nostr_events (
            id TEXT PRIMARY KEY,
            item_id TEXT,
            event_id TEXT NOT NULL,
            kind INTEGER NOT NULL,
            pubkey TEXT NOT NULL,
            raw_event TEXT NOT NULL,
            seen_at INTEGER NOT NULL,
            verified BOOLEAN NOT NULL DEFAULT false
        );
        """
    )
    await db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS zapwall.settings (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            creator_nostr_pubkey TEXT,
            creator_npub TEXT,
            relay_urls_json TEXT DEFAULT '{DEFAULT_RELAYS_JSON}',
            bot_relay_urls_json TEXT DEFAULT '{DEFAULT_RELAYS_JSON}',
            dm_mode TEXT NOT NULL DEFAULT 'nostrclient',
            signing_mode TEXT NOT NULL DEFAULT 'external',
            signer_private_key TEXT,
            bot_private_key TEXT,
            bot_public_key TEXT,
            sats_per_mb INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        );
        """
    )


async def m002_preview_media_urls(db: Database):
    columns = await db.fetchall("PRAGMA zapwall.table_info(items)")
    column_names = {column["name"] for column in columns}
    if "preview_media_urls_json" not in column_names:
        await db.execute(
            """
            ALTER TABLE zapwall.items
            ADD COLUMN preview_media_urls_json TEXT DEFAULT '[]'
            """
        )


async def m003_default_relays(db: Database):
    await db.execute(
        f"""
        UPDATE zapwall.settings
        SET relay_urls_json = '{DEFAULT_RELAYS_JSON}'
        WHERE relay_urls_json IS NULL OR relay_urls_json = '' OR relay_urls_json = '[]'
        """
    )
    await db.execute(
        f"""
        UPDATE zapwall.settings
        SET bot_relay_urls_json = '{DEFAULT_RELAYS_JSON}'
        WHERE bot_relay_urls_json IS NULL OR bot_relay_urls_json = '' OR bot_relay_urls_json = '[]'
        """
    )


async def m004_media_blobs(db: Database):
    await db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS zapwall.media (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            item_id TEXT,
            purpose TEXT NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            data {db.blob} NOT NULL,
            created_at INTEGER NOT NULL
        );
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS zapwall.zapwall_media_wallet_idx
        ON media (wallet);
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS zapwall.zapwall_media_item_idx
        ON media (item_id);
        """
    )
