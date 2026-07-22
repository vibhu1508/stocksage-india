"""
Portfolio read/write for the StockSage AI assistant.

Writes go through a confirm step in the agent, so these are the low-level DB ops.
Synchronous (SQLAlchemy) — call via asyncio.to_thread from the async agent.
"""

import logging
from typing import Any, Dict, List, Optional

from database import SessionLocal
from models import PortfolioHolding
from routers.auth import verify_token

logger = logging.getLogger(__name__)


def user_id_from_token(token: Optional[str]) -> Optional[int]:
    """Decode the JWT from the chat WS query param → user id (or None)."""
    if not token:
        return None
    payload = verify_token(token)
    if not payload:
        return None
    sub = payload.get("sub")
    try:
        return int(sub) if sub is not None else None
    except (TypeError, ValueError):
        return None


def get_user_holdings(user_id: int) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = db.query(PortfolioHolding).filter(PortfolioHolding.user_id == user_id).all()
        return [
            {
                "symbol": h.symbol,
                "type": h.instrument_type,
                "qty": h.qty,
                "avg_price": h.avg_price,
            }
            for h in rows
        ]
    except Exception:
        logger.exception("get_user_holdings failed for user %s", user_id)
        return []
    finally:
        db.close()


def record_equity_holding(user_id: int, symbol: str, qty: int, avg_price: float) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        holding = PortfolioHolding(
            user_id=user_id,
            symbol=str(symbol).upper().strip(),
            instrument_type="EQUITY",
            qty=int(qty),
            avg_price=float(avg_price),
            action="BUY",
        )
        db.add(holding)
        db.commit()
        db.refresh(holding)
        return {
            "ok": True,
            "holding_id": holding.id,
            "symbol": holding.symbol,
            "qty": holding.qty,
            "avg_price": holding.avg_price,
        }
    except Exception as exc:
        db.rollback()
        logger.exception("record_equity_holding failed")
        return {"ok": False, "error": str(exc)[:150]}
    finally:
        db.close()
