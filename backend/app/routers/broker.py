"""
Broker account management endpoints.

Every route is scoped to the authenticated user — there is no user_id in any
request body, so one user cannot read or alter another's brokerage link even by
guessing ids. (The existing /api/trade/ endpoint takes a user_id and checks it
against the token; that pattern is deliberately not repeated here.)

API keys are write-only from the client's perspective: they go in on link, and
no endpoint ever returns them, not even masked.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.crypto import encryption_available
from app.core.config import ALLOW_LIVE_TRADING, ALLOW_LIVE_BOT_TRADING
from app.routers.auth import get_current_user
from app.services.broker import (
    BrokerAuthError,
    BrokerError,
    BrokerNotLinked,
    LiveTradingDisabled,
    confirm_live_mode,
    delete_credentials,
    get_broker_for_user,
    get_link,
    reconcile_open_orders,
    save_credentials,
    set_enabled,
    sync_portfolio_from_broker,
)

router = APIRouter()


# --- Schemas ---

class LinkRequest(BaseModel):
    api_key: str = Field(..., min_length=8)
    secret_key: str = Field(..., min_length=8)


class LiveLinkRequest(LinkRequest):
    # A deliberate speed bump. The client must send this explicitly; there is no
    # default, so a copy-pasted paper-link request cannot accidentally go live.
    acknowledge_real_money: bool = Field(
        ...,
        description="Must be true. Confirms the user understands these keys trade real money.",
    )


class EnabledRequest(BaseModel):
    enabled: bool


# --- Helpers ---

def _link_payload(link) -> dict:
    if link is None:
        return {"linked": False, "mode": None, "is_enabled": False}
    return {
        "linked": True,
        "provider": link.provider,
        "mode": link.mode,
        "is_enabled": link.is_enabled,
        "broker_account_id": link.broker_account_id,
        "linked_at": link.linked_at,
        "live_confirmed": link.live_confirmed_at is not None,
        "last_sync_at": link.last_sync_at,
    }


# --- Routes ---

@router.get("/api/broker/status")
def broker_status(current_user: dict = Depends(get_current_user)):
    """Link state plus the server-side gates, so the UI can explain why live is
    unavailable instead of just failing when the user tries."""
    link = get_link(current_user["user_id"])
    return {
        **_link_payload(link),
        "encryption_configured": encryption_available(),
        "server_allows_live": ALLOW_LIVE_TRADING,
        "server_allows_live_bot": ALLOW_LIVE_BOT_TRADING,
    }


@router.post("/api/broker/link")
def link_paper_account(body: LinkRequest, current_user: dict = Depends(get_current_user)):
    """Link an Alpaca PAPER account. Credentials are verified before being stored."""
    if not encryption_available():
        raise HTTPException(
            status_code=503,
            detail="Credential encryption is not configured on the server "
                   "(BROKER_ENCRYPTION_KEY missing). Refusing to store API keys.",
        )
    try:
        link = save_credentials(
            current_user["user_id"], body.api_key, body.secret_key, mode="paper"
        )
    except BrokerAuthError as exc:
        raise HTTPException(status_code=400, detail=f"Alpaca rejected these keys: {exc}")
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Pull the paper account's starting balance and any existing positions in
    # immediately, so the portfolio page isn't empty right after linking.
    try:
        sync_portfolio_from_broker(current_user["user_id"])
    except BrokerError:
        pass

    return _link_payload(link)


@router.post("/api/broker/link/live")
def link_live_account(body: LiveLinkRequest, current_user: dict = Depends(get_current_user)):
    """Promote to LIVE trading with a real-money Alpaca key pair.

    Requires: server-wide ALLOW_LIVE_TRADING, a live key pair (Alpaca issues
    different credentials for live and paper), and an explicit acknowledgement.
    """
    if not body.acknowledge_real_money:
        raise HTTPException(
            status_code=400,
            detail="acknowledge_real_money must be true to enable live trading.",
        )
    if not encryption_available():
        raise HTTPException(
            status_code=503,
            detail="Credential encryption is not configured. Refusing to store live API keys.",
        )
    try:
        link = confirm_live_mode(current_user["user_id"], body.api_key, body.secret_key)
    except LiveTradingDisabled as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except BrokerAuthError as exc:
        raise HTTPException(status_code=400, detail=f"Alpaca rejected these live keys: {exc}")
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        sync_portfolio_from_broker(current_user["user_id"])
    except BrokerError:
        pass

    return _link_payload(link)


@router.post("/api/broker/enabled")
def set_broker_enabled(body: EnabledRequest, current_user: dict = Depends(get_current_user)):
    """Pause or resume broker routing. While paused, trades fall back to simulation."""
    link = get_link(current_user["user_id"])
    if link is None:
        raise HTTPException(status_code=404, detail="No linked broker account.")
    return _link_payload(set_enabled(current_user["user_id"], body.enabled))


@router.delete("/api/broker/unlink")
def unlink_account(current_user: dict = Depends(get_current_user)):
    """Delete stored credentials. Trade history is retained."""
    removed = delete_credentials(current_user["user_id"])
    if not removed:
        raise HTTPException(status_code=404, detail="No linked broker account.")
    return {"message": "Broker account unlinked.", "linked": False}


@router.get("/api/broker/account")
def broker_account(current_user: dict = Depends(get_current_user)):
    """Live account snapshot straight from Alpaca."""
    try:
        broker = get_broker_for_user(current_user["user_id"])
        if broker is None:
            raise HTTPException(status_code=404, detail="No enabled broker account.")
        return broker.get_account()
    except LiveTradingDisabled as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/api/broker/positions")
def broker_positions(current_user: dict = Depends(get_current_user)):
    try:
        broker = get_broker_for_user(current_user["user_id"])
        if broker is None:
            raise HTTPException(status_code=404, detail="No enabled broker account.")
        return broker.get_positions()
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/api/broker/clock")
def broker_clock(current_user: dict = Depends(get_current_user)):
    """Authoritative market open/close, including holidays and half days."""
    try:
        broker = get_broker_for_user(current_user["user_id"])
        if broker is None:
            raise HTTPException(status_code=404, detail="No enabled broker account.")
        return broker.get_clock()
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/api/broker/sync")
def sync_now(current_user: dict = Depends(get_current_user)):
    """Force a refresh of local balance and holdings from Alpaca."""
    try:
        return sync_portfolio_from_broker(current_user["user_id"])
    except BrokerNotLinked as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/api/broker/reconcile")
def reconcile_now(current_user: dict = Depends(get_current_user)):
    """Update any still-working orders with their current broker status."""
    try:
        return reconcile_open_orders(current_user["user_id"])
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
