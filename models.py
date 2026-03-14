from __future__ import annotations

import json
import math
import time
from enum import Enum

from pydantic import BaseModel, Field


def timestamp_now() -> int:
    return int(time.time())


DEFAULT_RELAYS = [
    "wss://relay.damus.io",
    "wss://relay.primal.net",
    "wss://nos.lol",
    "wss://relay.nostr.band",
    "wss://offchain.pub",
]


class ZapwallItemKind(str, Enum):
    text = "text"
    image = "image"
    file = "file"
    dm = "dm"
    subscription = "subscription"


class ZapwallItemStatus(str, Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class ZapwallUnlockType(str, Enum):
    dm_link = "dm_link"
    dm_content = "dm_content"
    entitlement_only = "entitlement_only"


class ZapwallDMMode(str, Enum):
    nostrclient = "nostrclient"
    manual = "manual"


class ZapwallSigningMode(str, Enum):
    external = "external"
    internal = "internal"


class ZapwallCreator(BaseModel):
    id: str
    wallet: str
    nostr_pubkey: str | None = None
    nostr_npub: str | None = None
    display_name: str | None = None
    profile_json: str | None = "{}"
    created_at: int = Field(default_factory=timestamp_now)
    updated_at: int = Field(default_factory=timestamp_now)

    @property
    def profile(self) -> dict:
        return json.loads(self.profile_json or "{}")


class ZapwallItem(BaseModel):
    id: str
    wallet: str
    creator_id: str
    slug: str
    title: str
    kind: ZapwallItemKind = ZapwallItemKind.text
    preview_text: str = ""
    full_text: str = ""
    price: int = Field(..., ge=1)
    currency: str = "sats"
    status: ZapwallItemStatus = ZapwallItemStatus.draft
    preview_event_id: str | None = None
    preview_event_raw: str | None = None
    cover_image: str | None = None
    preview_media_urls_json: str | None = "[]"
    media_urls_json: str | None = "[]"
    unlock_type: ZapwallUnlockType = ZapwallUnlockType.dm_link
    exact_amount_only: bool = False
    auto_dm_unlock: bool = True
    expires_at: int | None = None
    created_at: int = Field(default_factory=timestamp_now)
    updated_at: int = Field(default_factory=timestamp_now)

    @property
    def media_urls(self) -> list[str]:
        return json.loads(self.media_urls_json or "[]")

    @property
    def preview_media_urls(self) -> list[str]:
        return json.loads(self.preview_media_urls_json or "[]")

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at < timestamp_now())


class ZapwallPurchase(BaseModel):
    id: str
    item_id: str
    creator_id: str
    buyer_pubkey: str
    buyer_npub: str | None = None
    zap_event_id: str | None = None
    payment_hash: str | None = None
    amount_paid: int = Field(..., ge=0)
    unlock_token: str
    unlock_sent: bool = False
    unlock_sent_at: int | None = None
    created_at: int = Field(default_factory=timestamp_now)


class ZapwallReceipt(BaseModel):
    id: str
    purchase_id: str
    item_id: str
    buyer_pubkey: str
    receipt_payload: str
    receipt_signature: str
    created_at: int = Field(default_factory=timestamp_now)
    expires_at: int | None = None


class ZapwallNostrEvent(BaseModel):
    id: str
    item_id: str | None = None
    event_id: str
    kind: int
    pubkey: str
    raw_event: str
    seen_at: int = Field(default_factory=timestamp_now)
    verified: bool = False


class ZapwallSettings(BaseModel):
    id: str
    wallet: str
    user_id: str
    creator_nostr_pubkey: str | None = None
    creator_npub: str | None = None
    relay_urls_json: str | None = json.dumps(DEFAULT_RELAYS)
    bot_relay_urls_json: str | None = json.dumps(DEFAULT_RELAYS)
    dm_mode: ZapwallDMMode = ZapwallDMMode.nostrclient
    signing_mode: ZapwallSigningMode = ZapwallSigningMode.external
    signer_private_key: str | None = None
    bot_private_key: str | None = None
    bot_public_key: str | None = None
    sats_per_mb: int = Field(0, ge=0)
    updated_at: int = Field(default_factory=timestamp_now)

    def __init__(self, **data):
        for key in ("relay_urls_json", "bot_relay_urls_json"):
            value = data.get(key)
            if value is not None and not isinstance(value, str):
                data[key] = json.dumps(value)
        super().__init__(**data)

    @property
    def relay_urls(self) -> list[str]:
        return json.loads(self.relay_urls_json or json.dumps(DEFAULT_RELAYS))

    @property
    def bot_relay_urls(self) -> list[str]:
        return json.loads(self.bot_relay_urls_json or json.dumps(DEFAULT_RELAYS))


class CreatorNostrProfile(BaseModel):
    nostr_pubkey: str | None = None
    nostr_npub: str | None = None
    display_name: str | None = None
    profile: dict = Field(default_factory=dict)


class UpdateZapwallSettings(BaseModel):
    creator_nostr_pubkey: str | None = None
    relay_urls: list[str] = Field(default_factory=list)
    bot_relay_urls: list[str] = Field(default_factory=list)
    dm_mode: ZapwallDMMode = ZapwallDMMode.nostrclient
    signing_mode: ZapwallSigningMode = ZapwallSigningMode.external
    signer_private_key: str | None = None
    bot_private_key: str | None = None
    sats_per_mb: int | None = Field(None, ge=0)
    display_name: str | None = None
    profile: dict = Field(default_factory=dict)


class CreateZapwallItem(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    slug: str | None = Field(None, max_length=255)
    kind: ZapwallItemKind = ZapwallItemKind.text
    preview_text: str = ""
    full_text: str = ""
    price: int = Field(..., ge=1)
    cover_image: str | None = None
    preview_media_urls: list[str] = Field(default_factory=list)
    media_urls: list[str] = Field(default_factory=list)
    media_upload_bytes: int = Field(0, ge=0)
    unlock_type: ZapwallUnlockType = ZapwallUnlockType.dm_link
    exact_amount_only: bool = False
    auto_dm_unlock: bool = True
    expires_at: int | None = None
    status: ZapwallItemStatus = ZapwallItemStatus.draft


class UpdateZapwallItem(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(None, max_length=255)
    kind: ZapwallItemKind | None = None
    preview_text: str | None = None
    full_text: str | None = None
    price: int | None = Field(None, ge=1)
    cover_image: str | None = None
    preview_media_urls: list[str] | None = None
    media_urls: list[str] | None = None
    media_upload_bytes: int | None = Field(None, ge=0)
    unlock_type: ZapwallUnlockType | None = None
    exact_amount_only: bool | None = None
    auto_dm_unlock: bool | None = None
    expires_at: int | None = None
    status: ZapwallItemStatus | None = None
    preview_event_id: str | None = None
    preview_event_raw: str | None = None


class ZapwallPublicItem(BaseModel):
    id: str
    title: str
    kind: ZapwallItemKind
    preview_text: str
    price: int
    currency: str = "sats"
    creator_pubkey: str | None = None
    preview_event_id: str | None = None
    unlock_mode: ZapwallUnlockType
    cover_image: str | None = None
    preview_media_urls: list[str] = Field(default_factory=list)
    media_urls: list[str] = Field(default_factory=list)
    status: ZapwallItemStatus
    expires_at: int | None = None


class CreateInvoiceRequest(BaseModel):
    buyer_pubkey: str | None = None
    buyer_npub: str | None = None
    amount: int | None = Field(None, ge=1)
    memo: str | None = None


class InvoiceResponse(BaseModel):
    payment_hash: str
    payment_request: str
    amount: int
    price: int
    exact_amount_only: bool


class PurchaseStatusResponse(BaseModel):
    has_access: bool
    payment_hash: str | None = None
    paid: bool = False
    purchase_id: str | None = None
    unlock_token: str | None = None


class EntitlementResponse(BaseModel):
    has_access: bool
    receipt: str | None = None
    expires_at: int | None = None


class DashboardStats(BaseModel):
    items: int = 0
    sales_count: int = 0
    sats_earned: int = 0
    recent_unlocks: list[dict] = Field(default_factory=list)


class PreviewPublishResponse(BaseModel):
    published: bool
    event_id: str
    event: dict
    relays: list[str] = Field(default_factory=list)


class DMDeliveryResponse(BaseModel):
    sent: bool
    event_id: str | None = None
    event: dict | None = None
    message: str
    relays: list[str] = Field(default_factory=list)


class ZapReceiptNotification(BaseModel):
    item_id: str | None = None
    preview_event_id: str | None = None
    buyer_pubkey: str
    buyer_npub: str | None = None
    amount: int = Field(..., ge=1)
    zap_event_id: str | None = None
    payment_hash: str | None = None
    event: dict | None = None


class UnlockContentResponse(BaseModel):
    item: ZapwallPublicItem
    full_text: str
    media_urls: list[str] = Field(default_factory=list)
    receipt: str | None = None


def compute_minimum_price(upload_bytes: int, sats_per_mb: int) -> int:
    if not upload_bytes or not sats_per_mb:
        return 0
    return math.ceil((upload_bytes / (1024 * 1024)) * sats_per_mb)


class UnlockTokenPayload(BaseModel):
    item_id: str
    buyer_pubkey: str
    purchase_id: str
    created_at: int = Field(default_factory=timestamp_now)


class NostrPublishRequest(BaseModel):
    content: str | None = None


class NostrProfileResponse(BaseModel):
    relays: list[str] = Field(default_factory=list)
    creator_pubkey: str | None = None
    bot_pubkey: str | None = None
