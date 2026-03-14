from __future__ import annotations
from http import HTTPStatus

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from lnbits.core.crud import get_user
from lnbits.core.models import CreateInvoice, WalletTypeInfo
from lnbits.core.services import create_payment_request
from lnbits.decorators import require_admin_key, require_invoice_key
from lnbits.extensions.nostrclient.helpers import normalize_public_key
from lnbits.helpers import urlsafe_short_hash

from .crud import (
    create_item,
    create_media,
    get_dashboard_stats,
    get_item,
    get_item_by_preview_event_id,
    get_item_purchases,
    get_items,
    get_latest_receipt_for_purchase,
    get_or_create_creator,
    get_or_create_settings,
    get_media,
    get_media_total_size,
    get_purchase_by_unlock_token,
    get_purchase_by_zap_event,
    get_purchase_for_item_pubkey,
    get_settings,
    get_wallet_items,
    update_creator,
    update_item,
    update_settings,
)
from .helpers import (
    json_dumps,
    media_id_from_url,
    media_ids_from_urls,
    media_url,
    slugify,
    with_unlock_token,
)
from .models import (
    CreateInvoiceRequest,
    CreateZapwallItem,
    DashboardStats,
    EntitlementResponse,
    InvoiceResponse,
    NostrProfileResponse,
    NostrPublishRequest,
    PreviewPublishResponse,
    PurchaseStatusResponse,
    UnlockContentResponse,
    UpdateZapwallItem,
    UpdateZapwallSettings,
    ZapReceiptNotification,
    ZapwallItem,
    ZapwallItemStatus,
    ZapwallMedia,
    ZapwallMediaPurpose,
    ZapwallMediaUploadResponse,
    ZapwallPurchase,
    ZapwallPublicItem,
    ZapwallSettings,
    compute_minimum_price,
)
from .services.nostr import (
    build_preview_event,
    build_profile_event,
    get_npub,
    publish_preview_event,
    publish_signed_event,
)
from .services.payments import (
    create_access_purchase,
    finalize_invoice_payment,
    get_payment_status,
)
from .services.receipts import ensure_receipt_for_purchase

zapwall_api_router = APIRouter()


def _settings_for_client(settings: ZapwallSettings, creator) -> dict:
    safe_settings = settings.copy(
        update={"signer_private_key": None, "bot_private_key": None}
    )
    payload = jsonable_encoder(safe_settings)
    payload.update(
        {
            "display_name": creator.display_name,
            "profile": creator.profile,
            "signer_configured": bool(settings.signer_private_key),
            "bot_configured": bool(settings.bot_private_key),
        }
    )
    return payload


async def _item_media_upload_bytes(
    cover_image: str | None, preview_media_urls: list[str], media_urls: list[str]
) -> int:
    media_ids = media_ids_from_urls(preview_media_urls + media_urls)
    cover_media_id = media_id_from_url(cover_image)
    if cover_media_id:
        media_ids.append(cover_media_id)
    return await get_media_total_size(list(dict.fromkeys(media_ids)))


def _unlock_media_urls(urls: list[str], token: str) -> list[str]:
    return [with_unlock_token(url, token) for url in urls]


def _normalize_pubkey_or_400(pubkey: str) -> str:
    try:
        return normalize_public_key(pubkey)
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)
        ) from exc


async def _wallet_owner(wallet_info: WalletTypeInfo):
    user = await get_user(wallet_info.wallet.user)
    if not user:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="User not found.")
    return user


async def _wallet_settings(wallet_info: WalletTypeInfo) -> ZapwallSettings:
    return await get_or_create_settings(wallet_info.wallet.id, wallet_info.wallet.user)


async def _assert_item_wallet(
    item_id: str, wallet_info: WalletTypeInfo, write: bool = False
) -> ZapwallItem:
    item = await get_item(item_id)
    if not item:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found.")
    if write and item.wallet != wallet_info.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your item.")
    return item


@zapwall_api_router.get("/api/v1/dashboard")
async def api_dashboard(
    wallet_info: WalletTypeInfo = Depends(require_invoice_key),
) -> DashboardStats:
    return await get_dashboard_stats(wallet_info.wallet.id)


@zapwall_api_router.get("/api/v1/items")
async def api_items(
    all_wallets: bool = Query(False),
    wallet_info: WalletTypeInfo = Depends(require_invoice_key),
) -> list[ZapwallItem]:
    if not all_wallets:
        return await get_wallet_items(wallet_info.wallet.id)
    user = await _wallet_owner(wallet_info)
    return await get_items(user.wallet_ids)


@zapwall_api_router.post("/api/v1/items", status_code=HTTPStatus.CREATED)
async def api_create_item(
    data: CreateZapwallItem, wallet_info: WalletTypeInfo = Depends(require_admin_key)
) -> ZapwallItem:
    settings = await _wallet_settings(wallet_info)
    upload_bytes = (
        await _item_media_upload_bytes(
            data.cover_image, data.preview_media_urls, data.media_urls
        )
        + data.media_upload_bytes
    )
    minimum_price = compute_minimum_price(upload_bytes, settings.sats_per_mb)
    if minimum_price and data.price < minimum_price:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Price must be at least {minimum_price} sats for this upload size.",
        )

    creator = await get_or_create_creator(wallet_info.wallet.id, wallet_info.wallet.name)
    item = ZapwallItem(
        id=urlsafe_short_hash(),
        wallet=wallet_info.wallet.id,
        creator_id=creator.id,
        slug=slugify(data.slug or data.title),
        title=data.title,
        kind=data.kind,
        preview_text=data.preview_text,
        full_text=data.full_text,
        price=data.price,
        cover_image=data.cover_image,
        preview_media_urls_json=json_dumps(data.preview_media_urls),
        media_urls_json=json_dumps(data.media_urls),
        unlock_type=data.unlock_type,
        exact_amount_only=data.exact_amount_only,
        auto_dm_unlock=data.auto_dm_unlock,
        expires_at=data.expires_at,
        status=data.status,
    )
    existing = await get_wallet_items(wallet_info.wallet.id)
    if any(existing_item.slug == item.slug for existing_item in existing):
        item.slug = f"{item.slug}-{urlsafe_short_hash()[:6]}"
    return await create_item(item)


@zapwall_api_router.put("/api/v1/items/{item_id}")
async def api_update_item(
    item_id: str,
    data: UpdateZapwallItem,
    wallet_info: WalletTypeInfo = Depends(require_admin_key),
) -> ZapwallItem:
    item = await _assert_item_wallet(item_id, wallet_info, write=True)
    settings = await _wallet_settings(wallet_info)
    if data.media_upload_bytes is not None:
        preview_media_urls = (
            data.preview_media_urls
            if data.preview_media_urls is not None
            else item.preview_media_urls
        )
        media_urls = data.media_urls if data.media_urls is not None else item.media_urls
        cover_image = data.cover_image if data.cover_image is not None else item.cover_image
        upload_bytes = (
            await _item_media_upload_bytes(cover_image, preview_media_urls, media_urls)
            + data.media_upload_bytes
        )
        minimum_price = compute_minimum_price(
            upload_bytes, settings.sats_per_mb
        )
        new_price = data.price if data.price is not None else item.price
        if minimum_price and new_price < minimum_price:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=f"Price must be at least {minimum_price} sats for this upload size.",
            )
    for field, value in data.dict(exclude_unset=True).items():
        if field == "preview_media_urls" and value is not None:
            setattr(item, "preview_media_urls_json", json_dumps(value))
            continue
        if field == "media_urls" and value is not None:
            setattr(item, "media_urls_json", json_dumps(value))
            continue
        if field == "slug" and value:
            setattr(item, field, slugify(value))
            continue
        setattr(item, field, value)
    return await update_item(item)


@zapwall_api_router.delete("/api/v1/items/{item_id}", status_code=HTTPStatus.NO_CONTENT)
async def api_delete_item(
    item_id: str, wallet_info: WalletTypeInfo = Depends(require_admin_key)
):
    from .crud import delete_item

    item = await _assert_item_wallet(item_id, wallet_info, write=True)
    await delete_item(item.id)
    return None


@zapwall_api_router.get("/api/v1/items/{item_id}/buyers")
async def api_item_buyers(
    item_id: str, wallet_info: WalletTypeInfo = Depends(require_invoice_key)
) -> list[ZapwallPurchase]:
    item = await _assert_item_wallet(item_id, wallet_info, write=True)
    return await get_item_purchases(item.id)


@zapwall_api_router.get("/api/v1/settings")
async def api_get_settings(
    wallet_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    settings = await _wallet_settings(wallet_info)
    creator = await get_or_create_creator(wallet_info.wallet.id, wallet_info.wallet.name)
    return _settings_for_client(settings, creator)


@zapwall_api_router.put("/api/v1/settings")
async def api_update_settings(
    data: UpdateZapwallSettings,
    wallet_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    user = await _wallet_owner(wallet_info)
    settings = await _wallet_settings(wallet_info)
    creator = await get_or_create_creator(wallet_info.wallet.id, wallet_info.wallet.name)
    update_data = data.dict(exclude_unset=True)

    if "creator_nostr_pubkey" in update_data and update_data["creator_nostr_pubkey"]:
        normalized_pubkey = _normalize_pubkey_or_400(
            update_data["creator_nostr_pubkey"]
        )
        creator.nostr_pubkey = normalized_pubkey
        creator.nostr_npub = get_npub(normalized_pubkey)
        settings.creator_nostr_pubkey = normalized_pubkey
        settings.creator_npub = creator.nostr_npub
    if "display_name" in update_data:
        creator.display_name = update_data["display_name"]
    if "profile" in update_data:
        creator.profile_json = json_dumps(update_data["profile"])
    await update_creator(creator)

    if creator.nostr_pubkey:
        settings.creator_nostr_pubkey = creator.nostr_pubkey
    if creator.nostr_npub:
        settings.creator_npub = creator.nostr_npub
    if "relay_urls" in update_data:
        settings.relay_urls_json = json_dumps(update_data["relay_urls"])
    if "bot_relay_urls" in update_data:
        settings.bot_relay_urls_json = json_dumps(update_data["bot_relay_urls"])
    if "dm_mode" in update_data:
        settings.dm_mode = update_data["dm_mode"]
    if "signing_mode" in update_data:
        settings.signing_mode = update_data["signing_mode"]
    if "signer_private_key" in update_data:
        settings.signer_private_key = update_data["signer_private_key"]
    if "bot_private_key" in update_data:
        settings.bot_private_key = update_data["bot_private_key"]
        from lnbits.extensions.nostrclient.nostr.key import PrivateKey

        if settings.bot_private_key:
            if settings.bot_private_key.startswith("nsec1"):
                settings.bot_public_key = PrivateKey.from_nsec(
                    settings.bot_private_key
                ).public_key.hex()
            else:
                settings.bot_public_key = PrivateKey(
                    bytes.fromhex(settings.bot_private_key)
                ).public_key.hex()
    if "sats_per_mb" in update_data:
        if not user.super_user:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="Only super users can update sats_per_mb.",
            )
        settings.sats_per_mb = update_data["sats_per_mb"] or 0
    settings = await update_settings(settings)
    return _settings_for_client(settings, creator)


@zapwall_api_router.get("/api/v1/nostr/profile")
async def api_nostr_profile(
    wallet_info: WalletTypeInfo = Depends(require_invoice_key),
) -> NostrProfileResponse:
    settings = await _wallet_settings(wallet_info)
    return NostrProfileResponse(
        relays=settings.relay_urls,
        creator_pubkey=settings.creator_nostr_pubkey,
        bot_pubkey=settings.bot_public_key,
    )


@zapwall_api_router.post("/api/v1/media/upload")
async def api_upload_media(
    file: UploadFile = File(...),
    purpose: ZapwallMediaPurpose = Form(...),
    item_id: str | None = Form(None),
    wallet_info: WalletTypeInfo = Depends(require_admin_key),
) -> ZapwallMediaUploadResponse:
    item = None
    if item_id:
        item = await _assert_item_wallet(item_id, wallet_info, write=True)
    if purpose != ZapwallMediaPurpose.profile_picture and not item_id:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="item_id is required for item media uploads.",
        )
    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="Uploaded file is empty."
        )
    content_type = file.content_type or "application/octet-stream"
    media = ZapwallMedia(
        id=urlsafe_short_hash(),
        wallet=wallet_info.wallet.id,
        item_id=item.id if item else None,
        purpose=purpose,
        filename=file.filename or f"{purpose.value}-{urlsafe_short_hash()[:6]}",
        content_type=content_type,
        size_bytes=len(contents),
        data=contents,
    )
    await create_media(media)
    return ZapwallMediaUploadResponse(
        id=media.id,
        url=media_url(media.id),
        filename=media.filename,
        content_type=media.content_type,
        size_bytes=media.size_bytes,
        purpose=media.purpose,
    )


@zapwall_api_router.get("/api/v1/media/{media_id}")
async def api_get_media_blob(media_id: str, token: str | None = None) -> Response:
    media = await get_media(media_id)
    if not media:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Media not found.")
    if media.purpose == ZapwallMediaPurpose.unlock_media:
        if not token:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="Unlock token is required for protected media.",
            )
        purchase = await get_purchase_by_unlock_token(token)
        if not purchase or purchase.item_id != media.item_id:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="Invalid unlock token for this media.",
            )
    headers = {"Cache-Control": "public, max-age=3600"}
    if media.purpose == ZapwallMediaPurpose.unlock_media:
        headers["Cache-Control"] = "private, max-age=300"
    headers["Content-Disposition"] = f'inline; filename="{media.filename}"'
    return Response(content=media.data, media_type=media.content_type, headers=headers)


@zapwall_api_router.post("/api/v1/items/{item_id}/publish-preview")
async def api_publish_preview(
    item_id: str,
    payload: NostrPublishRequest,
    wallet_info: WalletTypeInfo = Depends(require_admin_key),
) -> PreviewPublishResponse:
    item = await _assert_item_wallet(item_id, wallet_info, write=True)
    settings = await _wallet_settings(wallet_info)
    creator = await get_or_create_creator(wallet_info.wallet.id, wallet_info.wallet.name)
    event = await build_preview_event(item, settings, creator, payload.content)
    item.preview_event_id = event["id"]
    item.preview_event_raw = json_dumps(event)
    published = False
    relays = settings.relay_urls
    if settings.signing_mode.value == "internal" and settings.signer_private_key:
        event = await publish_preview_event(event, settings.signer_private_key)
        published = True
        item.preview_event_id = event["id"]
        item.preview_event_raw = json_dumps(event)
    item.status = ZapwallItemStatus.published
    await update_item(item)
    return PreviewPublishResponse(
        published=published, event_id=event["id"], event=event, relays=relays
    )


@zapwall_api_router.post("/api/v1/profile/publish")
async def api_publish_profile(
    wallet_info: WalletTypeInfo = Depends(require_admin_key),
) -> PreviewPublishResponse:
    settings = await _wallet_settings(wallet_info)
    creator = await get_or_create_creator(wallet_info.wallet.id, wallet_info.wallet.name)
    event = await build_profile_event(settings, creator)
    published = False
    relays = settings.relay_urls
    if settings.signing_mode.value == "internal" and settings.signer_private_key:
        event = await publish_signed_event(event, settings.signer_private_key)
        published = True
    return PreviewPublishResponse(
        published=published,
        event_id=event["id"],
        event=event,
        relays=relays,
    )


@zapwall_api_router.get("/api/v1/items/{item_id}")
async def api_public_item(item_id: str) -> ZapwallPublicItem:
    item = await get_item(item_id)
    if not item or item.status != ZapwallItemStatus.published:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found.")
    settings = await get_settings(item.wallet)
    return ZapwallPublicItem(
        id=item.id,
        title=item.title,
        kind=item.kind,
        preview_text=item.preview_text,
        price=item.price,
        currency=item.currency,
        creator_pubkey=settings.creator_nostr_pubkey if settings else None,
        preview_event_id=item.preview_event_id,
        unlock_mode=item.unlock_type,
        cover_image=item.cover_image,
        preview_media_urls=item.preview_media_urls,
        media_urls=[],
        status=item.status,
        expires_at=item.expires_at,
    )


@zapwall_api_router.post("/api/v1/items/{item_id}/invoice")
async def api_create_invoice(
    item_id: str,
    data: CreateInvoiceRequest,
    request: Request,
) -> InvoiceResponse:
    item = await get_item(item_id)
    if not item or item.status != ZapwallItemStatus.published:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found.")
    if not data.buyer_pubkey:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="buyer_pubkey is required for invoice fallback unlocks.",
        )
    buyer_pubkey = _normalize_pubkey_or_400(data.buyer_pubkey)
    amount = data.amount or item.price
    if item.exact_amount_only and amount != item.price:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Exact amount of {item.price} sats is required.",
        )
    if amount < item.price:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Minimum unlock amount is {item.price} sats.",
        )
    invoice = CreateInvoice(
        out=False,
        amount=amount,
        unit="sat",
        memo=data.memo or f"Zapwall unlock for {item.title}",
        extra={
            "tag": "zapwall",
            "item_id": item.id,
            "wallet_id": item.wallet,
            "buyer_pubkey": buyer_pubkey,
            "buyer_npub": data.buyer_npub,
            "base_url": str(request.base_url),
        },
    )
    payment = await create_payment_request(item.wallet, invoice)
    return InvoiceResponse(
        payment_hash=payment.payment_hash,
        payment_request=payment.bolt11,
        amount=amount,
        price=item.price,
        exact_amount_only=item.exact_amount_only,
    )


@zapwall_api_router.get("/api/v1/items/{item_id}/status")
async def api_item_status(
    item_id: str,
    pubkey: str | None = None,
    payment_hash: str | None = None,
) -> PurchaseStatusResponse:
    item = await get_item(item_id)
    if not item:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found.")
    if pubkey:
        purchase = await get_purchase_for_item_pubkey(
            item_id, _normalize_pubkey_or_400(pubkey)
        )
        if purchase:
            return PurchaseStatusResponse(
                has_access=True,
                paid=True,
                purchase_id=purchase.id,
            )
    if payment_hash:
        purchase = await finalize_invoice_payment(item, payment_hash)
        if purchase:
            return PurchaseStatusResponse(
                has_access=True,
                payment_hash=payment_hash,
                paid=True,
                purchase_id=purchase.id,
                unlock_token=purchase.unlock_token,
            )
        paid = await get_payment_status(item, payment_hash)
        return PurchaseStatusResponse(
            has_access=False, payment_hash=payment_hash, paid=paid
        )
    return PurchaseStatusResponse(has_access=False, paid=False)


@zapwall_api_router.get("/api/v1/unlock/{token}")
async def api_unlock(token: str) -> UnlockContentResponse:
    purchase = await get_purchase_by_unlock_token(token)
    if not purchase:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Unlock token not found."
        )
    item = await get_item(purchase.item_id)
    if not item:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found.")
    settings = await get_settings(item.wallet)
    receipt = await get_latest_receipt_for_purchase(purchase.id)
    public_item = ZapwallPublicItem(
        id=item.id,
        title=item.title,
        kind=item.kind,
        preview_text=item.preview_text,
        price=item.price,
        currency=item.currency,
        creator_pubkey=settings.creator_nostr_pubkey if settings else None,
        preview_event_id=item.preview_event_id,
        unlock_mode=item.unlock_type,
        cover_image=item.cover_image,
        preview_media_urls=item.preview_media_urls,
        media_urls=_unlock_media_urls(item.media_urls, token),
        status=item.status,
        expires_at=item.expires_at,
    )
    return UnlockContentResponse(
        item=public_item,
        full_text=item.full_text,
        media_urls=_unlock_media_urls(item.media_urls, token),
        receipt=receipt.receipt_payload if receipt else None,
    )


@zapwall_api_router.get("/api/v1/items/{item_id}/entitlement")
async def api_entitlement(
    item_id: str,
    pubkey: str,
) -> EntitlementResponse:
    purchase = await get_purchase_for_item_pubkey(item_id, _normalize_pubkey_or_400(pubkey))
    if not purchase:
        return EntitlementResponse(has_access=False, receipt=None, expires_at=None)
    receipt = await ensure_receipt_for_purchase(purchase)
    return EntitlementResponse(
        has_access=True,
        receipt=receipt.receipt_payload,
        expires_at=receipt.expires_at,
    )


@zapwall_api_router.post("/api/v1/zaps/notify")
async def api_zaps_notify(
    data: ZapReceiptNotification,
    request: Request,
    wallet_info: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    if data.zap_event_id:
        existing = await get_purchase_by_zap_event(data.zap_event_id)
        if existing:
            return {"status": "duplicate", "purchase_id": existing.id}
    item = None
    if data.item_id:
        item = await get_item(data.item_id)
    elif data.preview_event_id:
        item = await get_item_by_preview_event_id(data.preview_event_id)
    if not item:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found.")
    if item.wallet != wallet_info.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your item.")
    if item.exact_amount_only and data.amount != item.price:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Exact amount of {item.price} sats required.",
        )
    if data.amount < item.price:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Minimum unlock amount is {item.price} sats.",
        )
    buyer_pubkey = _normalize_pubkey_or_400(data.buyer_pubkey)

    purchase, token = await create_access_purchase(
        item=item,
        buyer_pubkey=buyer_pubkey,
        amount_paid=data.amount,
        buyer_npub=data.buyer_npub,
        zap_event_id=data.zap_event_id,
        payment_hash=data.payment_hash,
        base_url=str(request.base_url),
    )
    return {
        "status": "ok",
        "purchase_id": purchase.id,
        "unlock_url": f"{request.base_url}zapwall/unlock/{token}",
        "unlock_token": token,
    }
