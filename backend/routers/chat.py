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

import asyncio
import logging
import os
import tempfile

from fastapi import APIRouter, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from services.agent import run_agent_stream, run_confirm_holding, run_cancel_holding
from services.portfolio_actions import user_id_from_token
from services.transcribe import SttUnavailable, stt_status, transcribe_file

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/voice-status")
async def voice_status():
    """Whether voice input is usable on this server, so clients can hide the mic."""
    return stt_status()


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Speech-to-text for voice input (works in any browser — the browser records,
    we transcribe with Whisper). Returns {text, language}."""
    status = stt_status()
    if not status.get("available"):
        # Answer through FastAPI (503 WITH CORS headers) rather than letting an
        # oversized model load and get the whole process OOM-killed.
        return JSONResponse(
            status_code=503,
            content={
                "text": "",
                "language": None,
                "error": status.get("reason", "voice_unavailable"),
                "detail": status.get("detail", "Voice input is unavailable."),
            },
        )

    data = await audio.read()
    if not data:
        return {"text": "", "language": None}
    suffix = os.path.splitext(audio.filename or "clip.webm")[1] or ".webm"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.close()
        return await asyncio.to_thread(transcribe_file, tmp.name)
    except SttUnavailable as exc:
        return JSONResponse(
            status_code=503,
            content={"text": "", "language": None, "error": "voice_unavailable", "detail": str(exc)},
        )
    except Exception:
        logger.exception("transcription failed")
        return {"text": "", "language": None, "error": "transcription failed"}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

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
