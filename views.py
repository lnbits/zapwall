from http import HTTPStatus
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from lnbits.core.crud import get_wallet
from lnbits.core.crud.users import get_user_from_account
from lnbits.core.crud.extensions import get_installed_extension
from lnbits.core.models.users import Account
from lnbits.decorators import check_admin
from lnbits.helpers import template_renderer

from .helpers import json_dumps, with_unlock_token
from .crud import (
    get_dashboard_stats,
    get_item,
    get_item_purchases,
    get_latest_receipt_for_purchase,
    get_or_create_creator,
    get_or_create_settings,
    get_purchase_by_unlock_token,
    get_wallet_items,
)
from .models import ZapwallPublicItem

zapwall_generic_router = APIRouter()


def zapwall_renderer():
    return template_renderer(["zapwall/templates"])


def _script_version() -> int:
    script_path = Path(__file__).parent / "static" / "js" / "index.js"
    return int(script_path.stat().st_mtime)


async def _page_context(account: Account):
    user = await get_user_from_account(account)
    if not user:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="User not found.")
    wallet_id = user.wallet_ids[0] if user.wallet_ids else None
    wallet = await get_wallet(wallet_id) if wallet_id else None
    if not wallet:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Wallet not found.")
    creator = await get_or_create_creator(wallet.id, wallet.name)
    settings = await get_or_create_settings(wallet.id, user.id)
    stats = await get_dashboard_stats(wallet.id)
    items = await get_wallet_items(wallet.id)
    nostrclient = await get_installed_extension("nostrclient")
    return {
        "account_user": user,
        "wallet": wallet,
        "creator": creator,
        "settings": settings,
        "stats": stats,
        "items": items,
        "nostrclient_active": bool(nostrclient and nostrclient.active),
    }


def _settings_seed(context: dict) -> dict:
    safe_settings = context["settings"].copy(
        update={"signer_private_key": None, "bot_private_key": None}
    )
    payload = jsonable_encoder(safe_settings)
    payload.update(
        {
            "display_name": context["creator"].display_name,
            "profile": context["creator"].profile,
            "signer_configured": bool(context["settings"].signer_private_key),
            "bot_configured": bool(context["settings"].bot_private_key),
        }
    )
    return payload


def _admin_payload(context: dict, page: str, **extra: dict) -> dict:
    return {
        "page": page,
        "wallet": jsonable_encoder(context["wallet"]),
        "stats": jsonable_encoder(context["stats"]),
        "settings": _settings_seed(context),
        "items": jsonable_encoder(context["items"]),
        "isSuperUser": context["account_user"].super_user,
        "nostrclientActive": context["nostrclient_active"],
        **extra,
    }


def _render_admin_page(request: Request, context: dict, page: str, **extra: dict):
    return zapwall_renderer().TemplateResponse(
        "zapwall/index.html",
        {
            "request": request,
            "user": context["account_user"].json(),
            "cache_version": _script_version(),
            "zapwall_data": _admin_payload(context, page, **extra),
            **context,
        },
    )


@zapwall_generic_router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, account: Account = Depends(check_admin)):
    context = await _page_context(account)
    return _render_admin_page(request, context, "settings")


@zapwall_generic_router.get("/items", response_class=HTMLResponse)
async def items_page(request: Request, account: Account = Depends(check_admin)):
    context = await _page_context(account)
    return _render_admin_page(request, context, "items")


@zapwall_generic_router.get("/items/new", response_class=HTMLResponse)
async def new_item_page(request: Request, account: Account = Depends(check_admin)):
    context = await _page_context(account)
    return _render_admin_page(request, context, "item", item=None, buyers=[])


@zapwall_generic_router.get("/items/{item_id}", response_class=HTMLResponse)
async def edit_item_page(
    request: Request, item_id: str, account: Account = Depends(check_admin)
):
    context = await _page_context(account)
    item = await get_item(item_id)
    if not item or item.wallet != context["wallet"].id:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found.")
    buyers = await get_item_purchases(item.id)
    return _render_admin_page(
        request,
        context,
        "item",
        item=jsonable_encoder(item),
        buyers=jsonable_encoder(buyers),
    )


@zapwall_generic_router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, account: Account = Depends(check_admin)):
    context = await _page_context(account)
    return _render_admin_page(request, context, "settings")


@zapwall_generic_router.get("/i/{item_id}", response_class=HTMLResponse)
async def public_item_page(request: Request, item_id: str):
    item = await get_item(item_id)
    if not item or item.status.value != "published":
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found.")
    public_item = ZapwallPublicItem(
        id=item.id,
        title=item.title,
        kind=item.kind,
        preview_text=item.preview_text,
        price=item.price,
        creator_pubkey=None,
        preview_event_id=item.preview_event_id,
        unlock_mode=item.unlock_type,
        cover_image=item.cover_image,
        preview_media_urls=item.preview_media_urls,
        media_urls=[],
        status=item.status,
        expires_at=item.expires_at,
    )
    return zapwall_renderer().TemplateResponse(
        "zapwall/public_item.html",
        {"request": request, "item": public_item, "item_full": item},
    )


@zapwall_generic_router.get("/unlock/{token}", response_class=HTMLResponse)
async def unlocked_item_page(request: Request, token: str):
    purchase = await get_purchase_by_unlock_token(token)
    if not purchase:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Unlock token not found."
        )
    item = await get_item(purchase.item_id)
    if not item:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Item not found.")
    item = item.copy(
        update={
            "media_urls_json": json_dumps(
                [with_unlock_token(url, token) for url in item.media_urls]
            )
        }
    )
    receipt = await get_latest_receipt_for_purchase(purchase.id)
    return zapwall_renderer().TemplateResponse(
        "zapwall/unlock.html",
        {
            "request": request,
            "item": item,
            "purchase": purchase,
            "receipt": receipt,
        },
    )
