"""
Broker integration layer (Alpaca).

Everything that touches a real brokerage lives behind this module. The rest of
the app talks to it through a small surface — `get_broker_for_user()`,
`AlpacaBroker.submit_order()`, `sync_portfolio_from_broker()` — so swapping in a
second provider later means writing another class with the same methods, not
rewriting the trading path.

Design notes
------------
Per-user accounts. Credentials live in `broker_accounts`, keyed by user_id, and
are decrypted only in memory at call time. A user with no linked account (or a
disabled one) keeps the original simulated behaviour, so nothing breaks for
accounts that never link a brokerage.

Alpaca is the source of truth. Once a user is linked, local `portfolios` and
`holdings` rows become a cache of Alpaca's account state, refreshed by
`sync_portfolio_from_broker()`. The old code hand-maintained that ledger and
would happily sell shares the user did not own; here the broker rejects the
oversell and local state is overwritten from the broker on the next sync.

Orders are asynchronous. A market order submitted outside regular hours sits as
`accepted` until the open. `submit_order()` polls briefly for a terminal state,
then records the trade as PENDING and lets `reconcile_open_orders()` finish the
job on a later scheduler tick.

Idempotency. Every order carries a `client_order_id`. If the process dies between
submitting and recording, the retry is rejected by Alpaca as a duplicate rather
than silently doubling the position.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from app.core.config import (
    ALLOW_LIVE_BOT_TRADING,
    ALLOW_LIVE_TRADING,
    BROKER_FILL_POLL_INTERVAL,
    BROKER_FILL_POLL_TIMEOUT,
)
from app.core.crypto import (
    CredentialDecryptionError,
    CredentialEncryptionUnavailable,
    decrypt,
    encrypt,
)
from app.core.database import get_db_connection


# --- Exceptions ---------------------------------------------------------------

class BrokerError(Exception):
    """Base for every broker-layer failure."""


class BrokerNotLinked(BrokerError):
    """User has no usable linked brokerage account."""


class BrokerAuthError(BrokerError):
    """Credentials were rejected by the broker."""


class BrokerRejected(BrokerError):
    """The broker refused the order (insufficient buying power, oversell, halted...)."""


class LiveTradingDisabled(BrokerError):
    """A live order was attempted while a live-trading gate is closed."""


# --- Status mapping -----------------------------------------------------------

# Alpaca exposes ~18 order states. The app only needs to know whether an order is
# still working, done, or dead — this collapses them.
_TERMINAL_FILLED = {"filled"}
_TERMINAL_DEAD = {"canceled", "expired", "rejected", "done_for_day", "stopped", "suspended"}
_PARTIAL = {"partially_filled"}


def _map_status(alpaca_status: str) -> str:
    status = (alpaca_status or "").lower()
    if status in _TERMINAL_FILLED:
        return "FILLED"
    if status in _PARTIAL:
        return "PARTIAL"
    if status in _TERMINAL_DEAD:
        return "REJECTED" if status == "rejected" else "CANCELED"
    return "PENDING"


def _is_terminal(local_status: str) -> bool:
    return local_status in ("FILLED", "CANCELED", "REJECTED")


# --- Data carriers ------------------------------------------------------------

@dataclass
class BrokerLink:
    """A user's stored brokerage link, minus the secrets."""
    user_id: int
    provider: str
    mode: str                      # 'paper' | 'live'
    is_enabled: bool
    broker_account_id: Optional[str]
    linked_at: Optional[str]
    live_confirmed_at: Optional[str]
    last_sync_at: Optional[str]

    @property
    def is_live(self) -> bool:
        return self.mode == "live"


@dataclass
class OrderResult:
    """Outcome of submitting one order."""
    broker_order_id: str
    client_order_id: str
    status: str                    # PENDING | PARTIAL | FILLED | CANCELED | REJECTED
    symbol: str
    side: str
    submitted_qty: int
    filled_qty: int
    filled_avg_price: Optional[float]
    raw_status: str

    @property
    def is_terminal(self) -> bool:
        return _is_terminal(self.status)

    @property
    def effective_price(self) -> Optional[float]:
        return self.filled_avg_price


# --- Credential storage -------------------------------------------------------

def save_credentials(
    user_id: int,
    api_key: str,
    secret_key: str,
    mode: str = "paper",
    provider: str = "alpaca",
) -> BrokerLink:
    """Encrypt and store a user's broker credentials, replacing any existing link.

    Credentials are verified against the broker BEFORE being written, so a typo
    fails loudly at link time instead of silently at the first trade.

    Always stores mode='paper' unless explicitly told otherwise; promoting to live
    goes through `confirm_live_mode()`.
    """
    if mode not in ("paper", "live"):
        raise ValueError("mode must be 'paper' or 'live'")

    # Verify before persisting.
    probe = AlpacaBroker(api_key=api_key, secret_key=secret_key, paper=(mode == "paper"), user_id=user_id)
    account = probe.get_account()

    try:
        api_key_enc = encrypt(api_key)
        secret_key_enc = encrypt(secret_key)
    except CredentialEncryptionUnavailable:
        # Deliberately not caught and downgraded — refusing to store is correct.
        raise

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO broker_accounts
                (user_id, provider, api_key_encrypted, secret_key_encrypted, mode,
                 is_enabled, broker_account_id, linked_at, live_confirmed_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP, NULL)
            ON CONFLICT(user_id) DO UPDATE SET
                provider = excluded.provider,
                api_key_encrypted = excluded.api_key_encrypted,
                secret_key_encrypted = excluded.secret_key_encrypted,
                mode = excluded.mode,
                is_enabled = 1,
                broker_account_id = excluded.broker_account_id,
                linked_at = CURRENT_TIMESTAMP,
                -- Re-linking clears any prior live confirmation on purpose:
                -- new keys must be re-acknowledged before they can trade live.
                live_confirmed_at = NULL
            """,
            (user_id, provider, api_key_enc, secret_key_enc, mode, account.get("account_number")),
        )
        conn.commit()
    finally:
        conn.close()

    return get_link(user_id)


def get_link(user_id: int) -> Optional[BrokerLink]:
    """Return the user's broker link metadata, or None if they have not linked one."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, provider, mode, is_enabled, broker_account_id,
                   linked_at, live_confirmed_at, last_sync_at
            FROM broker_accounts WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return None

    return BrokerLink(
        user_id=row["user_id"],
        provider=row["provider"],
        mode=row["mode"],
        is_enabled=bool(row["is_enabled"]),
        broker_account_id=row["broker_account_id"],
        linked_at=row["linked_at"],
        live_confirmed_at=row["live_confirmed_at"],
        last_sync_at=row["last_sync_at"],
    )


def delete_credentials(user_id: int) -> bool:
    """Unlink a brokerage. Local trade history is kept; only the keys go away."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM broker_accounts WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def set_enabled(user_id: int, enabled: bool) -> Optional[BrokerLink]:
    """Pause or resume broker routing without discarding stored keys."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE broker_accounts SET is_enabled = ? WHERE user_id = ?",
            (1 if enabled else 0, user_id),
        )
        conn.commit()
    finally:
        conn.close()
    return get_link(user_id)


def confirm_live_mode(user_id: int, api_key: str, secret_key: str) -> BrokerLink:
    """Promote a user to live trading.

    Deliberately requires a fresh key pair rather than flipping a flag on the
    existing row. Alpaca issues *different* credentials for paper and live, so a
    "switch to live" that reused the paper keys would fail at the first order
    anyway — and demanding the live keys makes the consequence explicit at the
    moment of the decision rather than at the moment of the trade.
    """
    if not ALLOW_LIVE_TRADING:
        raise LiveTradingDisabled(
            "Live trading is disabled server-wide. Set ALLOW_LIVE_TRADING=true to enable it."
        )

    probe = AlpacaBroker(api_key=api_key, secret_key=secret_key, paper=False, user_id=user_id)
    account = probe.get_account()

    api_key_enc = encrypt(api_key)
    secret_key_enc = encrypt(secret_key)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO broker_accounts
                (user_id, provider, api_key_encrypted, secret_key_encrypted, mode,
                 is_enabled, broker_account_id, linked_at, live_confirmed_at)
            VALUES (?, 'alpaca', ?, ?, 'live', 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                api_key_encrypted = excluded.api_key_encrypted,
                secret_key_encrypted = excluded.secret_key_encrypted,
                mode = 'live',
                is_enabled = 1,
                broker_account_id = excluded.broker_account_id,
                live_confirmed_at = CURRENT_TIMESTAMP
            """,
            (user_id, api_key_enc, secret_key_enc, account.get("account_number")),
        )
        conn.commit()
    finally:
        conn.close()

    return get_link(user_id)


def revert_to_paper(user_id: int, api_key: str, secret_key: str) -> BrokerLink:
    """Drop back to paper trading with the user's paper key pair."""
    return save_credentials(user_id, api_key, secret_key, mode="paper")


# --- Broker client ------------------------------------------------------------

class AlpacaBroker:
    """Thin wrapper over alpaca-py's TradingClient, scoped to one user's account."""

    def __init__(self, api_key: str, secret_key: str, paper: bool, user_id: Optional[int] = None):
        self.user_id = user_id
        self.paper = paper
        self._client = TradingClient(api_key=api_key, secret_key=secret_key, paper=paper)

    # -- account ---------------------------------------------------------------

    def get_account(self) -> Dict:
        """Account snapshot. Doubles as the credential validity check."""
        try:
            acct = self._client.get_account()
        except APIError as exc:
            raise self._translate(exc) from exc

        return {
            "account_number": getattr(acct, "account_number", None),
            "status": str(getattr(acct, "status", "")),
            "cash": float(getattr(acct, "cash", 0) or 0),
            "buying_power": float(getattr(acct, "buying_power", 0) or 0),
            "equity": float(getattr(acct, "equity", 0) or 0),
            "portfolio_value": float(getattr(acct, "portfolio_value", 0) or 0),
            "currency": getattr(acct, "currency", "USD"),
            # Alpaca blocks the account itself when these are set — surface them
            # so the UI can explain *why* orders are bouncing.
            "trading_blocked": bool(getattr(acct, "trading_blocked", False)),
            "account_blocked": bool(getattr(acct, "account_blocked", False)),
            "pattern_day_trader": bool(getattr(acct, "pattern_day_trader", False)),
            "daytrade_count": int(getattr(acct, "daytrade_count", 0) or 0),
        }

    def get_positions(self) -> List[Dict]:
        """Open positions as plain dicts."""
        try:
            positions = self._client.get_all_positions()
        except APIError as exc:
            raise self._translate(exc) from exc

        out = []
        for p in positions:
            out.append({
                "symbol": p.symbol,
                "qty": int(float(p.qty)),
                "avg_entry_price": float(p.avg_entry_price),
                "market_value": float(p.market_value or 0),
                "unrealized_pl": float(p.unrealized_pl or 0),
                "current_price": float(p.current_price or 0),
            })
        return out

    def get_clock(self) -> Dict:
        """Market open/close state, straight from the broker.

        Worth preferring over the scheduler's hand-rolled hour arithmetic, which
        does not know about holidays or half days.
        """
        try:
            clock = self._client.get_clock()
        except APIError as exc:
            raise self._translate(exc) from exc
        return {
            "is_open": bool(clock.is_open),
            "next_open": clock.next_open.isoformat() if clock.next_open else None,
            "next_close": clock.next_close.isoformat() if clock.next_close else None,
        }

    # -- orders ----------------------------------------------------------------

    def submit_order(
        self,
        ticker: str,
        action: str,
        quantity: int,
        client_order_id: Optional[str] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        wait_for_fill: bool = True,
    ) -> OrderResult:
        """Submit a market order and optionally wait briefly for it to settle.

        Returns an OrderResult whose status may still be PENDING — that is normal
        and expected outside market hours. Callers must not assume a fill.
        """
        side = OrderSide.BUY if action.upper() == "BUY" else OrderSide.SELL
        coid = client_order_id or f"ts-{uuid.uuid4().hex[:24]}"

        request = MarketOrderRequest(
            symbol=ticker.upper(),
            qty=int(quantity),
            side=side,
            time_in_force=time_in_force,
            client_order_id=coid,
        )

        try:
            order = self._client.submit_order(request)
        except APIError as exc:
            raise self._translate(exc) from exc

        result = self._to_result(order)

        if wait_for_fill and not result.is_terminal:
            result = self._poll_until_terminal(result.broker_order_id, result)

        return result

    def get_order(self, broker_order_id: str) -> OrderResult:
        try:
            order = self._client.get_order_by_id(broker_order_id)
        except APIError as exc:
            raise self._translate(exc) from exc
        return self._to_result(order)

    def cancel_order(self, broker_order_id: str) -> None:
        try:
            self._client.cancel_order_by_id(broker_order_id)
        except APIError as exc:
            raise self._translate(exc) from exc

    def _poll_until_terminal(self, broker_order_id: str, initial: OrderResult) -> OrderResult:
        """Poll an order for a short window, then give up and leave it PENDING."""
        deadline = time.monotonic() + BROKER_FILL_POLL_TIMEOUT
        latest = initial
        while time.monotonic() < deadline:
            time.sleep(BROKER_FILL_POLL_INTERVAL)
            try:
                latest = self.get_order(broker_order_id)
            except BrokerError:
                # Transient read failure shouldn't invalidate a submitted order —
                # the reconciler will catch up with it later.
                return latest
            if latest.is_terminal:
                return latest
        return latest

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _to_result(order) -> OrderResult:
        raw_status = str(getattr(order.status, "value", order.status))
        filled_qty = int(float(order.filled_qty or 0))
        avg_price = order.filled_avg_price
        return OrderResult(
            broker_order_id=str(order.id),
            client_order_id=order.client_order_id,
            status=_map_status(raw_status),
            symbol=order.symbol,
            side=str(getattr(order.side, "value", order.side)).upper(),
            submitted_qty=int(float(order.qty or 0)),
            filled_qty=filled_qty,
            filled_avg_price=float(avg_price) if avg_price is not None else None,
            raw_status=raw_status,
        )

    @staticmethod
    def _translate(exc: APIError) -> BrokerError:
        """Turn Alpaca's HTTP errors into something the app can branch on."""
        message = str(exc)
        status_code = getattr(exc, "status_code", None)

        if status_code in (401, 403):
            return BrokerAuthError(f"Broker rejected credentials: {message}")
        if status_code in (403, 422) or "insufficient" in message.lower():
            return BrokerRejected(f"Broker rejected order: {message}")
        return BrokerError(f"Broker error: {message}")


# --- Factory ------------------------------------------------------------------

def get_broker_for_user(user_id: int, is_bot_trade: bool = False) -> Optional[AlpacaBroker]:
    """Build a broker client for a user, or return None to mean "simulate instead".

    Returns None when the user has not linked an account or has paused routing.
    Raises when a link exists but cannot legally be used — the caller should
    surface that as an error rather than quietly falling back to simulation,
    because silently simulating a trade the user believes is real is the worst
    possible failure mode here.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT api_key_encrypted, secret_key_encrypted, mode, is_enabled, live_confirmed_at
            FROM broker_accounts WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row or not row["is_enabled"]:
        return None

    mode = row["mode"]
    is_live = mode == "live"

    if is_live:
        if not ALLOW_LIVE_TRADING:
            raise LiveTradingDisabled(
                "Live trading is disabled server-wide (ALLOW_LIVE_TRADING is off)."
            )
        if not row["live_confirmed_at"]:
            raise LiveTradingDisabled(
                "Live trading has not been confirmed for this account. Re-link with live keys."
            )
        if is_bot_trade and not ALLOW_LIVE_BOT_TRADING:
            raise LiveTradingDisabled(
                "The automated bot is not permitted to place live orders "
                "(ALLOW_LIVE_BOT_TRADING is off). Manual trades are still allowed."
            )

    try:
        api_key = decrypt(row["api_key_encrypted"])
        secret_key = decrypt(row["secret_key_encrypted"])
    except (CredentialDecryptionError, CredentialEncryptionUnavailable) as exc:
        raise BrokerAuthError(str(exc)) from exc

    return AlpacaBroker(
        api_key=api_key,
        secret_key=secret_key,
        paper=not is_live,
        user_id=user_id,
    )


# --- Portfolio sync -----------------------------------------------------------

def sync_portfolio_from_broker(user_id: int) -> Dict:
    """Overwrite local `portfolios` and `holdings` with Alpaca's account state.

    Alpaca is authoritative once linked. This is what keeps the existing
    portfolio UI and the RL model's observation (balance, shares, entry price)
    reading real numbers instead of a drifting local ledger.

    Holdings are replaced wholesale rather than diffed: a position closed outside
    the app (manually on Alpaca's site, or by a stop) must disappear locally, and
    a diff that only updates rows it recognises would leave it behind forever.
    """
    broker = get_broker_for_user(user_id)
    if broker is None:
        raise BrokerNotLinked(f"User {user_id} has no enabled broker account.")

    account = broker.get_account()
    positions = broker.get_positions()

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Cash, not equity: `portfolios.balance` is spent by BUYs, so it has to be
        # the uninvested cash figure. Using portfolio_value here would double-count
        # open positions and let the bot "spend" money already tied up in stock.
        cursor.execute(
            "UPDATE portfolios SET balance = ?, timestamp = CURRENT_TIMESTAMP WHERE user_id = ?",
            (account["cash"], user_id),
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO portfolios (user_id, balance) VALUES (?, ?)",
                (user_id, account["cash"]),
            )

        cursor.execute("DELETE FROM holdings WHERE user_id = ?", (user_id,))
        for pos in positions:
            if pos["qty"] <= 0:
                continue  # Shorts are out of scope: the schema assumes long-only.
            cursor.execute(
                "INSERT INTO holdings (user_id, ticker, quantity, purchase_price) VALUES (?, ?, ?, ?)",
                (user_id, pos["symbol"], pos["qty"], pos["avg_entry_price"]),
            )

        cursor.execute(
            "UPDATE broker_accounts SET last_sync_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "cash": account["cash"],
        "equity": account["equity"],
        "buying_power": account["buying_power"],
        "positions": len(positions),
        "trading_blocked": account["trading_blocked"],
    }


# --- Order reconciliation -----------------------------------------------------

def reconcile_open_orders(user_id: int) -> Dict:
    """Bring locally-PENDING trades up to date with the broker.

    Orders submitted outside market hours, or that partially fill, leave rows in
    PENDING. This is called on each scheduler tick so those rows eventually reach
    a terminal status with the real fill price, instead of sitting in the trade
    history forever at their optimistic submission price.
    """
    broker = get_broker_for_user(user_id)
    if broker is None:
        return {"checked": 0, "updated": 0}

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT trade_id, broker_order_id FROM trades
            WHERE user_id = ? AND status IN ('PENDING', 'PARTIAL')
              AND broker_order_id IS NOT NULL
            """,
            (user_id,),
        )
        pending = cursor.fetchall()
    finally:
        conn.close()

    updated = 0
    for row in pending:
        try:
            result = broker.get_order(row["broker_order_id"])
        except BrokerError as exc:
            print(f"⚠️  Reconcile failed for order {row['broker_order_id']}: {exc}")
            continue

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE trades
                SET status = ?, filled_qty = ?, filled_avg_price = ?,
                    price = COALESCE(?, price)
                WHERE trade_id = ?
                """,
                (
                    result.status,
                    result.filled_qty,
                    result.filled_avg_price,
                    result.filled_avg_price,
                    row["trade_id"],
                ),
            )
            conn.commit()
            updated += 1
        finally:
            conn.close()

    if updated:
        # Any status change moves cash or shares, so refresh the cached ledger.
        try:
            sync_portfolio_from_broker(user_id)
        except BrokerError as exc:
            print(f"⚠️  Post-reconcile sync failed for user {user_id}: {exc}")

    return {"checked": len(pending), "updated": updated}
