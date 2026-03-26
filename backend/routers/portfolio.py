"""
Portfolio Router - user-specific holdings management
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, Literal, Any, cast

from database import get_db
from models import PortfolioHolding, User
from routers.auth import get_current_user
from routers import strategy_builder as strategy_builder_router

router = APIRouter()


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
