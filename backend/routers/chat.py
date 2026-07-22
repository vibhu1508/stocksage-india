"""
StockSage AI assistant — chat WebSocket.

`WS /api/chat/ws?token=<jwt>` runs the streaming agent loop. The token is used to
identify the signed-in user for portfolio tools; read-only market tools work
without it.

Client → server: {"message": "<user text>"}
                 {"action": "confirm_holding", "holding": {symbol, quantity, avg_price}}
                 {"action": "cancel_holding"}
Server → client: {"type": "token", "text": ...}       (streamed answer chunks)
                 {"type": "tool", "name": ...}         (a tool is running)
                 {"type": "confirm_request", "holding": {...}}  (ask user to confirm a write)
                 {"type": "done"}                      (turn complete)
                 {"type": "error", "detail": ...}
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.agent import run_agent_stream, run_confirm_holding, run_cancel_holding
from services.portfolio_actions import user_id_from_token

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_HISTORY_MESSAGES = 40


@router.websocket("/ws")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()
    user_id = user_id_from_token(websocket.query_params.get("token"))
    history: list[dict] = []
    # Remembers the holding awaiting confirmation, so a confirm click can't be spoofed
    # with different values than what the user was shown.
    pending_holding: dict | None = None

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            try:
                if action == "confirm_holding":
                    holding = pending_holding or data.get("holding") or {}
                    pending_holding = None
                    async for event in run_confirm_holding(history, holding, user_id):
                        await websocket.send_json(event)
                elif action == "cancel_holding":
                    pending_holding = None
                    async for event in run_cancel_holding(history):
                        await websocket.send_json(event)
                else:
                    user_message = str(data.get("message", "")).strip()
                    if not user_message:
                        continue
                    history.append({"role": "user", "content": user_message})
                    async for event in run_agent_stream(history, user_id):
                        if event.get("type") == "confirm_request":
                            pending_holding = event.get("holding")
                        await websocket.send_json(event)
            except Exception:
                logger.exception("agent turn failed")
                await websocket.send_json(
                    {"type": "error", "detail": "Something went wrong. Please try again."}
                )

            if len(history) > MAX_HISTORY_MESSAGES:
                history = history[-MAX_HISTORY_MESSAGES:]
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("chat websocket error")
        try:
            await websocket.close()
        except Exception:
            pass
