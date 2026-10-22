"""
StockSage AI assistant — chat WebSocket.

`WS /api/chat/ws?token=<jwt>` runs the streaming agent loop. A valid, unrevoked
session is required (it also identifies the user for portfolio tools); otherwise
the socket sends an error and closes with 1008.

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

from fastapi import APIRouter, Depends, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from models import User
from routers.auth import authenticate_websocket, get_current_user
from services.agent import run_agent_stream, run_confirm_holding, run_cancel_holding
from services.redis_store import is_rate_limited
from services.transcribe import SttUnavailable, stt_status, transcribe_file

logger = logging.getLogger(__name__)

router = APIRouter()

# ~5 minutes of opus/AAC voice; caps memory and STT quota per request.
MAX_AUDIO_BYTES = 5 * 1024 * 1024
MAX_MESSAGE_CHARS = 2000
# Per user, enforced in Redis. shortcut: fails open when Redis is not configured; fine for the
# invite-only pilot, must be a hard limit before public access.
CHAT_TURNS_PER_MINUTE = int(os.getenv("CHAT_TURNS_PER_MINUTE", "15"))
TRANSCRIBES_PER_MINUTE = int(os.getenv("TRANSCRIBES_PER_MINUTE", "10"))
RATE_LIMITED_DETAIL = "You're sending requests too quickly. Please wait a minute and try again."


@router.get("/voice-status")
async def voice_status():
    """Whether voice input is usable on this server, so clients can hide the mic."""
    return stt_status()


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Speech-to-text for voice input (works in any browser — the browser records,
    we transcribe with Whisper). Returns {text, language}."""
    if await is_rate_limited(f"stt:rl:{current_user.id}", TRANSCRIBES_PER_MINUTE, 60):
        return JSONResponse(
            status_code=429,
            content={"text": "", "language": None, "error": "rate_limited", "detail": RATE_LIMITED_DETAIL},
        )
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

    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if not data:
        return {"text": "", "language": None}
    if len(data) > MAX_AUDIO_BYTES:
        return JSONResponse(
            status_code=413,
            content={"text": "", "language": None, "error": "audio_too_large", "detail": "Recording is too long."},
        )
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
    user = authenticate_websocket(websocket)
    if not user:
        await websocket.send_json({"type": "error", "detail": "Please sign in to use StockSage AI."})
        await websocket.close(code=1008)
        return
    user_id = user.id
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
                    # Only the holding the server proposed may be written, never one from the client.
                    holding = pending_holding
                    pending_holding = None
                    if not holding:
                        await websocket.send_json(
                            {"type": "error", "detail": "This request has expired. Please ask again."}
                        )
                        continue
                    async for event in run_confirm_holding(history, holding, user_id):
                        await websocket.send_json(event)
                elif action == "cancel_holding":
                    pending_holding = None
                    async for event in run_cancel_holding(history):
                        await websocket.send_json(event)
                else:
                    user_message = str(data.get("message", "")).strip()[:MAX_MESSAGE_CHARS]
                    if not user_message:
                        continue
                    if await is_rate_limited(f"chat:rl:{user_id}", CHAT_TURNS_PER_MINUTE, 60):
                        await websocket.send_json({"type": "error", "detail": RATE_LIMITED_DETAIL})
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
