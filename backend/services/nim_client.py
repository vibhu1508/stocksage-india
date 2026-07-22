"""
NVIDIA NIM client for the StockSage AI assistant.

NIM is OpenAI-API-compatible, so we use the `openai` SDK pointed at NIM's
`/v1` endpoint. Models and base URL are configured via environment variables so
the brain can be swapped without code changes.

Note: on the free NIM tier, 70B models (e.g. meta/llama-3.3-70b-instruct) do not
return within a usable latency, so the default primary is
`nvidia/llama-3.3-nemotron-super-49b-v1` (NVIDIA's Llama-3.3-derived model), which
supports streaming + tool calling and responds reliably. Change NIM_MODEL to the
70B on a paid/self-hosted deployment.
"""

import os
from functools import lru_cache

from openai import AsyncOpenAI, OpenAI

NIM_BASE_URL = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
# Primary "brain" — reasoning + tool calling.
NIM_MODEL = os.getenv("NIM_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1")
# Cheap/fast workhorse — routing, classification, compliance checks, sentiment.
NIM_MODEL_FAST = os.getenv("NIM_MODEL_FAST", "meta/llama-3.1-8b-instruct")


@lru_cache(maxsize=1)
def get_nim_client() -> OpenAI:
    """Return a cached NIM client. Raises if the API key is not configured."""
    api_key = os.getenv("NVIDIA_NIM_API_KEY")
    if not api_key:
        raise RuntimeError(
            "NVIDIA_NIM_API_KEY is not set — add it to backend/.env to enable the AI assistant."
        )
    return OpenAI(base_url=NIM_BASE_URL, api_key=api_key, timeout=90.0, max_retries=1)


@lru_cache(maxsize=1)
def get_async_nim_client() -> AsyncOpenAI:
    """Async NIM client for the streaming chat agent (non-blocking in FastAPI)."""
    api_key = os.getenv("NVIDIA_NIM_API_KEY")
    if not api_key:
        raise RuntimeError(
            "NVIDIA_NIM_API_KEY is not set — add it to backend/.env to enable the AI assistant."
        )
    return AsyncOpenAI(base_url=NIM_BASE_URL, api_key=api_key, timeout=90.0, max_retries=1)


def stream_deltas(stream):
    """Yield text content deltas from a NIM chat.completions stream, skipping
    empty/usage chunks (NIM emits trailing chunks with no `choices`)."""
    for chunk in stream:
        if not chunk.choices:
            continue
        content = chunk.choices[0].delta.content
        if content:
            yield content
