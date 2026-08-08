"""
Speech-to-text for the assistant (English / Hindi / Hinglish).

Two providers:

* **nim** (default) — NVIDIA-hosted `whisper-large-v3` over Riva gRPC. Free with
  the existing NIM key, and nothing loads into this process, so the API can't be
  OOM-killed by it. Best accuracy of the options we tested.
* **local** — self-hosted faster-whisper. Kept for offline development.
  WARNING: the weights load into THIS process ('medium' is ~1.4 GB). On a small
  instance that is an OOM kill, which takes every other endpoint down with it —
  and an OOM is a SIGKILL, so it cannot be caught. Hence local is opt-in and
  refuses models bigger than STT_MEMORY_BUDGET_MB.

The browser uploads webm/opus and the mobile app uploads m4a/AAC; Riva accepts
neither, so audio is decoded to 16 kHz mono PCM WAV first (verified: raw webm is
rejected with INVALID_ARGUMENT, transcoded audio transcribes perfectly).
"""

import importlib.util
import io
import logging
import os
import wave
from functools import lru_cache

logger = logging.getLogger(__name__)

# "nim" (hosted, no RAM cost) or "local" (self-hosted faster-whisper).
STT_PROVIDER = os.getenv("STT_PROVIDER", "nim").strip().lower()

# NVIDIA-hosted whisper-large-v3 (NVCF). Works on the free NIM tier.
NIM_ASR_URI = os.getenv("NIM_ASR_URI", "grpc.nvcf.nvidia.com:443")
NIM_ASR_FUNCTION_ID = os.getenv(
    "NIM_ASR_FUNCTION_ID", "b702f636-f60c-4a3d-a6f4-f3568c13bd7d"
)
# "multi" = auto-detect. Do NOT hardcode a language: forcing en-US turns Hindi
# speech into confident nonsense ("भाव" → "importance") rather than failing.
NIM_ASR_LANGUAGE = os.getenv("NIM_ASR_LANGUAGE", "multi")

# --- local provider only ---
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
STT_ENABLED = os.getenv("STT_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
_MODEL_FOOTPRINT_MB = {
    "tiny": 120, "base": 200, "small": 600,
    "medium": 1600, "large-v2": 3200, "large-v3": 3200,
}
_MEMORY_BUDGET_MB = int(os.getenv("STT_MEMORY_BUDGET_MB", "1800"))

_TARGET_RATE = 16000

# Bias transcription toward Indian-market vocabulary and common tickers.
_BIAS_PROMPT = (
    "Indian stock market query. Terms: Reliance, TCS, HDFC, Infosys, Axis Bank, SBI, "
    "Nifty, Sensex, BankNifty, share, price, bhav, market, portfolio, sentiment, news."
)


class SttUnavailable(RuntimeError):
    """Raised when speech-to-text is disabled or cannot safely run here."""


def _nim_key() -> str:
    return os.getenv("NVIDIA_NIM_API_KEY", "").strip()


def stt_status() -> dict:
    """Why STT is (un)available — the API returns this so clients can explain themselves."""
    if STT_PROVIDER == "nim":
        if not _nim_key():
            return {
                "available": False,
                "reason": "not_configured",
                "detail": "Voice input needs NVIDIA_NIM_API_KEY to be set on the server.",
            }
        # A stale build cache can ship the code without its dependencies; say so
        # plainly instead of reporting every attempt as "transcription failed".
        if importlib.util.find_spec("riva") is None:
            return {
                "available": False,
                "reason": "missing_dependency",
                "detail": (
                    "Voice input needs the 'nvidia-riva-client' package, which is not "
                    "installed on this server. Redeploy with a cleared build cache."
                ),
            }
        return {"available": True, "provider": "nim", "model": "whisper-large-v3"}

    if not STT_ENABLED:
        return {
            "available": False,
            "reason": "disabled",
            "detail": "Voice input is not enabled on this server.",
        }
    needed = _MODEL_FOOTPRINT_MB.get(WHISPER_MODEL, 0)
    if needed > _MEMORY_BUDGET_MB:
        return {
            "available": False,
            "reason": "insufficient_memory",
            "detail": (
                f"Whisper '{WHISPER_MODEL}' needs about {needed} MB, over the "
                f"{_MEMORY_BUDGET_MB} MB budget for this server."
            ),
        }
    return {"available": True, "provider": "local", "model": WHISPER_MODEL}


def _to_pcm_wav(path: str) -> bytes:
    """Decode any container (webm/opus, m4a/aac, wav…) to 16 kHz mono PCM WAV."""
    import av  # ships with faster-whisper; also listed explicitly in requirements
    import numpy as np

    container = av.open(path)
    resampler = av.audio.resampler.AudioResampler(
        format="s16", layout="mono", rate=_TARGET_RATE
    )
    chunks = []
    for frame in container.decode(audio=0):
        for resampled in resampler.resample(frame):
            chunks.append(resampled.to_ndarray())
    container.close()
    if not chunks:
        return b""

    pcm = np.concatenate(chunks, axis=1).astype("int16").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_TARGET_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


@lru_cache(maxsize=1)
def _nim_asr_service():
    import riva.client

    auth = riva.client.Auth(
        uri=NIM_ASR_URI,
        use_ssl=True,
        metadata_args=[
            ["function-id", NIM_ASR_FUNCTION_ID],
            ["authorization", f"Bearer {_nim_key()}"],
        ],
    )
    return riva.client.ASRService(auth)


def _guess_language(text: str) -> str:
    """Best-effort language tag; Riva's multi mode doesn't report one back."""
    return "hi" if any("ऀ" <= ch <= "ॿ" for ch in text) else "en"


def _transcribe_nim(path: str) -> dict:
    import riva.client

    audio = _to_pcm_wav(path)
    if not audio:
        return {"text": "", "language": None}

    config = riva.client.RecognitionConfig(
        language_code=NIM_ASR_LANGUAGE,
        max_alternatives=1,
        enable_automatic_punctuation=True,
    )
    response = _nim_asr_service().offline_recognize(audio, config)
    text = " ".join(
        alt.transcript
        for result in response.results
        for alt in result.alternatives
    ).strip()
    return {"text": text, "language": _guess_language(text)}


@lru_cache(maxsize=1)
def _local_model():
    from faster_whisper import WhisperModel

    logger.info("Loading Whisper model '%s' (first load downloads the weights)…", WHISPER_MODEL)
    return WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")


def _transcribe_local(path: str) -> dict:
    model = _local_model()
    segments, info = model.transcribe(path, beam_size=1, initial_prompt=_BIAS_PROMPT)
    text = " ".join(seg.text for seg in segments).strip()
    return {"text": text, "language": info.language}


def transcribe_file(path: str) -> dict:
    """Transcribe an audio file → {'text', 'language'}. Blocking — call in a thread.

    Raises SttUnavailable when voice is off or can't run here, so the caller can
    answer cleanly instead of the process being killed.
    """
    status = stt_status()
    if not status.get("available"):
        raise SttUnavailable(status.get("detail", "Voice input is unavailable."))

    if STT_PROVIDER == "nim":
        return _transcribe_nim(path)
    return _transcribe_local(path)
