"""
Server-side speech-to-text (Whisper) for the assistant.

Runs faster-whisper locally (free, self-hosted) so voice input works in EVERY
browser — the browser only records audio; transcription happens here. Multilingual
(English / Hindi / Hinglish). Model configurable via WHISPER_MODEL (default: small).
"""

import logging
import os
from functools import lru_cache

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")

# Bias transcription toward Indian-market vocabulary and common tickers.
_BIAS_PROMPT = (
    "Indian stock market query. Terms: Reliance, TCS, HDFC, Infosys, Axis Bank, SBI, "
    "Nifty, Sensex, BankNifty, share, price, bhav, market, portfolio, sentiment, news."
)


@lru_cache(maxsize=1)
def _get_model() -> WhisperModel:
    logger.info("Loading Whisper model '%s' (first load downloads the weights)…", WHISPER_MODEL)
    return WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")


def transcribe_file(path: str) -> dict:
    """Transcribe an audio file → {'text', 'language'}. Blocking — call in a thread."""
    model = _get_model()
    segments, info = model.transcribe(path, beam_size=1, initial_prompt=_BIAS_PROMPT)
    text = " ".join(seg.text for seg in segments).strip()
    return {"text": text, "language": info.language}
