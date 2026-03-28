"""
Portfolio Router - user-specific holdings management
"""

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, Literal, Any, cast
import asyncio
import time
import hashlib
from datetime import timezone

from database import get_db
from models import PortfolioHolding, User, UserSession
from routers.auth import get_current_user, verify_token
from routers import strategy_builder as strategy_builder_router

router = APIRouter()

_LIVE_PRICE_CACHE_TTL_SEC = 2.0
_LIVE_PRICE_CACHE: dict[str, tuple[float, float]] = {}


def _cache_get_live_price(cache_key: str) -> Optional[float]:
    cached = _LIVE_PRICE_CACHE.get(cache_key)
    if not cached:
        return None

    value, stored_at = cached
    if (time.time() - stored_at) > _LIVE_PRICE_CACHE_TTL_SEC:
        _LIVE_PRICE_CACHE.pop(cache_key, None)
        return None

    return value


def _cache_set_live_price(cache_key: str, value: float) -> None:
    if value <= 0:
        return
    _LIVE_PRICE_CACHE[cache_key] = (value, time.time())


def _extract_ltp(payload: Any) -> Optional[float]:
    """Extract LTP robustly from NSE response variants."""
    if payload is None:
        return None

    if isinstance(payload, (int, float)):
        value = float(payload)
        return value if value > 0 else None

    if isinstance(payload, str):
        try:
            value = float(payload)
            return value if value > 0 else None
        except Exception:
            return None

    if isinstance(payload, list):
        for item in payload:
            extracted = _extract_ltp(item)
            if extracted is not None:
                return extracted
        return None

    if not isinstance(payload, dict):
        return None

    preferred_keys = [
        "lastPrice",
        "last",
        "ltp",
        "lastTradedPrice",
        "close",
    ]

    for key in preferred_keys:
        if key in payload:
            extracted = _extract_ltp(payload.get(key))
            if extracted is not None:
                return extracted

    nested_keys = ["priceInfo", "metadata", "nearestFuture", "CE", "PE"]
    for key in nested_keys:
        if key in payload:
            extracted = _extract_ltp(payload.get(key))
            if extracted is not None:
                return extracted

    # Fallback: scan all values once.
    for value in payload.values():
        extracted = _extract_ltp(value)
        if extracted is not None:
            return extracted

    return None


def _holding_side_multiplier(action: Optional[str], instrument_type: str) -> int:
    if instrument_type == "EQUITY":
        return 1
    return -1 if (action or "").strip().upper() == "SELL" else 1


def _find_option_ltp_from_chain(
    chain_payload: dict,
    strike: Optional[float],
    option_type: Optional[str],
) -> Optional[float]:
    option_side = (option_type or "CE").strip().upper()
    rows = chain_payload.get("filtered", {}).get("data") or chain_payload.get("data") or []

    def strike_matches(row_strike: Any) -> bool:
        if strike is None:
            return True
        try:
            return abs(float(row_strike) - float(strike)) <= 0.01
        except Exception:
            return False

    for row in rows:
        if not isinstance(row, dict):
            continue
        if not strike_matches(row.get("strikePrice") or row.get("strike")):
            continue

        leg_obj = row.get(option_side)
        ltp = _extract_ltp(leg_obj)
        if ltp is not None:
            return ltp

        # Flat key fallback when CE/PE object is not present.
        flat_candidates = [
            f"{option_side}_LTP",
            f"{option_side}Ltp",
            f"{option_side.lower()}Ltp",
            f"{option_side}LastPrice",
        ]
        for key in flat_candidates:
            if key in row:
                ltp = _extract_ltp(row.get(key))
                if ltp is not None:
                    return ltp

    return None


async def _resolve_equity_ltp(symbol: str) -> Optional[float]:
    payload = await strategy_builder_router.get_symbol_live_data(symbol)
    return _extract_ltp(payload)


async def _resolve_future_ltp(symbol: str, expiry: Optional[str]) -> Optional[float]:
    payload = await strategy_builder_router.get_futures_live_data(symbol=symbol, expiry=expiry)

    if isinstance(payload, dict):
        # Best effort expiry match if futuresData is available.
        futures_rows = payload.get("futuresData") or []
        if expiry and isinstance(futures_rows, list):
            expiry_upper = expiry.strip().upper()
            for row in futures_rows:
                if not isinstance(row, dict):
                    continue
                row_expiry = str(row.get("expiryDate") or row.get("expiry") or "").strip().upper()
                if row_expiry == expiry_upper:
                    ltp = _extract_ltp(row)
                    if ltp is not None:
                        return ltp

        ltp = _extract_ltp(payload.get("nearestFuture"))
        if ltp is not None:
            return ltp

    return _extract_ltp(payload)


async def _resolve_option_ltp(
    symbol: str,
    expiry: Optional[str],
    strike: Optional[float],
    option_type: Optional[str],
) -> Optional[float]:
    chain = await strategy_builder_router.get_option_chain_live_data(symbol=symbol, expiry=expiry)
    if isinstance(chain, dict):
        matched = _find_option_ltp_from_chain(chain, strike=strike, option_type=option_type)
        if matched is not None:
            return matched
    return _extract_ltp(chain)


async def _resolve_holding_ltp(model: Any) -> Optional[float]:
    symbol = (model.symbol or "").strip().upper()
    instrument_type = (model.instrument_type or "EQUITY").strip().upper()

    cache_key_parts = [
        symbol,
        instrument_type,
        str(model.expiry or ""),
        str(model.strike or ""),
        str(model.option_type or ""),
    ]
    cache_key = "|".join(cache_key_parts)
    cached = _cache_get_live_price(cache_key)
    if cached is not None:
        return cached

    if instrument_type == "EQUITY":
        ltp = await _resolve_equity_ltp(symbol)
    elif instrument_type == "FUTURE":
        ltp = await _resolve_future_ltp(symbol=symbol, expiry=model.expiry)
    elif instrument_type == "OPTION":
        ltp = await _resolve_option_ltp(
            symbol=symbol,
            expiry=model.expiry,
            strike=model.strike,
            option_type=model.option_type,
        )
    else:
        ltp = await _resolve_equity_ltp(symbol)

    if ltp is not None:
        _cache_set_live_price(cache_key, ltp)
    return ltp


async def _holding_live_snapshot(model: Any) -> dict:
    lot_size = _get_lot_size(model.symbol) if model.instrument_type in {"FUTURE", "OPTION"} else 1
    lots = (model.qty // lot_size) if lot_size > 0 else model.qty
    invested = float(model.qty) * float(model.avg_price)

    base = {
        "id": model.id,
        "symbol": model.symbol,
        "instrument_type": model.instrument_type,
        "qty": model.qty,
        "lots": lots,
        "lot_size": lot_size,
        "avg_price": model.avg_price,
        "invested": round(invested, 2),
        "expiry": model.expiry,
        "strike": model.strike,
        "option_type": model.option_type,
        "action": model.action,
        "notes": model.notes,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }

    try:
        live_price = await _resolve_holding_ltp(model)
    except Exception:
        live_price = None

    if live_price is None or live_price <= 0:
        base.update({
            "live_price": None,
            "current_value": None,
            "pnl": None,
            "pnl_pct": None,
            "live_available": False,
        })
        return base

    side = _holding_side_multiplier(model.action, model.instrument_type)
    pnl = (float(live_price) - float(model.avg_price)) * float(model.qty) * float(side)
    current_value = invested + pnl
    pnl_pct = (pnl / invested * 100.0) if invested > 0 else 0.0

    base.update({
        "live_price": round(float(live_price), 4),
        "current_value": round(current_value, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "live_available": True,
    })
    return base


async def _build_holdings_live_payload(db: Session, current_user: User) -> dict:
    holdings = (
        db.query(PortfolioHolding)
        .filter(PortfolioHolding.user_id == current_user.id)
        .order_by(PortfolioHolding.created_at.desc())
        .all()
    )

    live_rows = await asyncio.gather(*[_holding_live_snapshot(cast(Any, h)) for h in holdings])

    total_invested = 0.0
    total_current = 0.0
    total_pnl = 0.0
    live_count = 0

    for row in live_rows:
        invested = float(row.get("invested") or 0.0)
        total_invested += invested

        if row.get("live_available"):
            live_count += 1
            total_current += float(row.get("current_value") or 0.0)
            total_pnl += float(row.get("pnl") or 0.0)
        else:
            total_current += invested

    total_pnl_pct = (total_pnl / total_invested * 100.0) if total_invested > 0 else 0.0

    return {
        "count": len(live_rows),
        "live_count": live_count,
        "total_invested": round(total_invested, 2),
        "total_current_value": round(total_current, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "as_of": int(time.time()),
        "holdings": live_rows,
    }


def _extract_ws_token(websocket: WebSocket) -> Optional[str]:
    token = str(websocket.query_params.get("token", "")).strip()
    if token:
        return token

    auth_header = str(websocket.headers.get("authorization", "")).strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    return None


def _authenticate_ws_user(token: str, db: Session) -> Optional[User]:
    payload = verify_token(token)
    if not payload:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = (
        db.query(UserSession)
        .filter(UserSession.token_hash == token_hash, UserSession.is_valid == True)
        .first()
    )
    if not session:
        return None

    expires_at = session.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at <= time_now_utc():
        session.is_valid = False
        db.commit()
        return None

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        return None

    return user


def time_now_utc():
    from datetime import datetime
    return datetime.now(timezone.utc)


def _get_lot_size(symbol: str) -> int:
    symbol_upper = symbol.upper().strip()
    if not symbol_upper:
        return 1

    try:
        strategy_builder_router.fetch_fo_contracts()
        lot = strategy_builder_router._LOT_SIZE_CACHE.get(symbol_upper, 1)
        return max(1, int(lot))
    except Exception:
        return 1


class HoldingCreateRequest(BaseModel):
    symbol: str
    instrument_type: Literal["EQUITY", "FUTURE", "OPTION"] = "EQUITY"
    qty: Optional[int] = None
    lots: Optional[int] = None
    avg_price: float
    expiry: Optional[str] = None
    strike: Optional[float] = None
    option_type: Optional[Literal["CE", "PE"]] = None
    action: Optional[Literal["BUY", "SELL"]] = None
    notes: Optional[str] = None


class HoldingUpdateRequest(BaseModel):
    qty: Optional[int] = None
    lots: Optional[int] = None
    avg_price: Optional[float] = None
    expiry: Optional[str] = None
    strike: Optional[float] = None
    option_type: Optional[Literal["CE", "PE"]] = None
    action: Optional[Literal["BUY", "SELL"]] = None
    notes: Optional[str] = None


def _resolve_quantity_for_create(payload: HoldingCreateRequest) -> int:
    if payload.instrument_type == "EQUITY":
        if payload.qty is None or payload.qty <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be positive for equity holdings")
        return payload.qty

    lot_size = _get_lot_size(payload.symbol)
    if payload.lots is not None:
        if payload.lots <= 0:
            raise HTTPException(status_code=400, detail="Lots must be positive for derivative holdings")
        return payload.lots * lot_size

    if payload.qty is None or payload.qty <= 0:
        raise HTTPException(status_code=400, detail="Provide lots or quantity for derivative holdings")

    return payload.qty


async def _get_option_contracts_from_nse(symbol: str, expiry: Optional[str] = None) -> dict:
    symbol_upper = symbol.upper().strip()
    dropdowns = await strategy_builder_router.get_dropdown_data(symbol_upper)
    expiries = dropdowns.get("expiryDates") or dropdowns.get("expiryDate") or []
    strikes = dropdowns.get("strikePrices") or []

    selected_expiry = expiry if expiry in expiries else (expiries[0] if expiries else None)

    if selected_expiry:
        chain = await strategy_builder_router.get_option_chain_live_data(symbol_upper, expiry=selected_expiry)
        rows = chain.get("filtered", {}).get("data") or chain.get("data") or []
        strikes = sorted({float(row.get("strikePrice")) for row in rows if row.get("strikePrice") is not None})

    return {
        "symbol": symbol_upper,
        "source": "nse",
        "expiries": expiries,
        "strikes": strikes,
        "selected_expiry": selected_expiry,
    }


@router.get("/lot-size/{symbol}")
async def get_symbol_lot_size(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    return {
        "symbol": symbol.upper().strip(),
        "lot_size": _get_lot_size(symbol),
    }


@router.get("/derivatives/contracts/{symbol}")
async def get_derivative_contracts(
    symbol: str,
    instrument_type: Literal["FUTURE", "OPTION"] = Query("OPTION"),
    expiry: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    symbol_upper = symbol.upper().strip()
    if not symbol_upper:
        raise HTTPException(status_code=400, detail="Symbol is required")

    if instrument_type == "FUTURE":
        dropdowns = await strategy_builder_router.get_dropdown_data(symbol_upper)
        expiries = dropdowns.get("expiryDates") or dropdowns.get("expiryDate") or []
        return {
            "symbol": symbol_upper,
            "instrument_type": instrument_type,
            "source": "nse",
            "expiries": expiries,
            "strikes": [],
            "selected_expiry": expiries[0] if expiries else None,
        }

    data = await _get_option_contracts_from_nse(symbol_upper, expiry=expiry)

    data["instrument_type"] = instrument_type
    return data


@router.get("/holdings")
async def get_holdings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    holdings = (
        db.query(PortfolioHolding)
        .filter(PortfolioHolding.user_id == current_user.id)
        .order_by(PortfolioHolding.created_at.desc())
        .all()
    )

    result = []
    total_invested = 0.0

    for holding in holdings:
        model = cast(Any, holding)
        lot_size = _get_lot_size(model.symbol) if model.instrument_type in {"FUTURE", "OPTION"} else 1
        lots = (model.qty // lot_size) if lot_size > 0 else model.qty
        invested = float(model.qty) * float(model.avg_price)
        total_invested += invested
        result.append({
            "id": model.id,
            "symbol": model.symbol,
            "instrument_type": model.instrument_type,
            "qty": model.qty,
            "lots": lots,
            "lot_size": lot_size,
            "avg_price": model.avg_price,
            "invested": round(invested, 2),
            "expiry": model.expiry,
            "strike": model.strike,
            "option_type": model.option_type,
            "action": model.action,
            "notes": model.notes,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        })

    return {
        "count": len(result),
        "total_invested": round(total_invested, 2),
        "holdings": result,
    }


@router.get("/holdings/live")
async def get_holdings_live(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await _build_holdings_live_payload(db, current_user)


@router.websocket("/holdings/live/ws")
async def holdings_live_ws(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()

    token = _extract_ws_token(websocket)
    if not token:
        await websocket.send_json({"event": "error", "detail": "Authentication token is required"})
        await websocket.close(code=1008)
        return

    current_user = _authenticate_ws_user(token, db)
    if not current_user:
        await websocket.send_json({"event": "error", "detail": "Unauthorized"})
        await websocket.close(code=1008)
        return

    await websocket.send_json({
        "event": "subscribed",
        "stream": "portfolio_live",
        "interval_sec": 2,
    })

    failures = 0
    try:
        while True:
            try:
                payload = await _build_holdings_live_payload(db, current_user)
                await websocket.send_json({
                    "event": "portfolio_live_snapshot",
                    "data": payload,
                })
                failures = 0
            except Exception:
                failures += 1
                await websocket.send_json({
                    "event": "stream_warning",
                    "detail": "Unable to build live portfolio snapshot",
                    "failures": failures,
                })
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return


@router.post("/holdings")
async def add_holding(
    payload: HoldingCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if payload.avg_price <= 0:
        raise HTTPException(status_code=400, detail="Average price must be positive")

    resolved_qty = _resolve_quantity_for_create(payload)

    holding = PortfolioHolding(
        user_id=current_user.id,
        symbol=payload.symbol.upper().strip(),
        instrument_type=payload.instrument_type,
        qty=resolved_qty,
        avg_price=payload.avg_price,
        expiry=payload.expiry,
        strike=payload.strike,
        option_type=payload.option_type,
        action=payload.action,
        notes=payload.notes,
    )
    db.add(holding)
    db.commit()
    db.refresh(holding)

    return {
        "message": "Holding added successfully",
        "holding_id": holding.id,
    }


@router.put("/holdings/{holding_id}")
async def update_holding(
    holding_id: int,
    payload: HoldingUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    holding = (
        db.query(PortfolioHolding)
        .filter(
            PortfolioHolding.id == holding_id,
            PortfolioHolding.user_id == current_user.id,
        )
        .first()
    )

    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")

    model = cast(Any, holding)

    if payload.qty is not None:
        if payload.qty <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be positive")
        model.qty = payload.qty

    if payload.lots is not None:
        if model.instrument_type == "EQUITY":
            raise HTTPException(status_code=400, detail="Lots are only valid for derivative holdings")
        if payload.lots <= 0:
            raise HTTPException(status_code=400, detail="Lots must be positive")
        model.qty = payload.lots * _get_lot_size(model.symbol)

    if payload.avg_price is not None:
        if payload.avg_price <= 0:
            raise HTTPException(status_code=400, detail="Average price must be positive")
        model.avg_price = payload.avg_price

    if payload.expiry is not None:
        model.expiry = payload.expiry
    if payload.strike is not None:
        model.strike = payload.strike
    if payload.option_type is not None:
        model.option_type = payload.option_type
    if payload.action is not None:
        model.action = payload.action
    if payload.notes is not None:
        model.notes = payload.notes

    db.commit()

    return {"message": "Holding updated successfully"}


@router.delete("/holdings/{holding_id}")
async def delete_holding(
    holding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    holding = (
        db.query(PortfolioHolding)
        .filter(
            PortfolioHolding.id == holding_id,
            PortfolioHolding.user_id == current_user.id,
        )
        .first()
    )

    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")

    db.delete(holding)
    db.commit()

    return {"message": "Holding deleted successfully"}
