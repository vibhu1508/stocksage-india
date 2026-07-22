"""
StockSage AI agent loop — two-model design.

Router (llama-3.1-8b, native function-calling): reliably decides which tools to
call and gathers real data. We discard its prose.
Writer (sarvam-m): given the conversation + the gathered data, writes the final
answer in the user's language (English / Hindi / Hinglish) with the guardrails
(no financial advice) and the respectful "aap" tone. sarvam has the best Indian-
language quality but can't call tools — so it never has to.
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Dict, List

_IST = timezone(timedelta(hours=5, minutes=30))

from services.nim_client import get_async_nim_client, NIM_MODEL, NIM_MODEL_FAST
from services.agent_tools import TOOL_SCHEMAS, execute_tool

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 4
# sarvam-m is a hybrid-reasoning model; turn thinking off so we stream only the answer.
WRITER_EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}

_EMPTY_FALLBACK = (
    "माफ़ कीजिये, मैं अभी उत्तर नहीं दे पाया। कृपया दोबारा पूछिए। "
    "(Sorry, I couldn't answer just now — please ask again.)"
)

ROUTER_SYSTEM = """You are the tool router for a stock-market assistant. Your ONLY job is to
call the right tools to fetch the live data needed to answer the user's latest message. Do NOT
write a reply to the user — just call tools.
Identify the stock symbol(s) from the user's LATEST message ONLY. Do NOT reuse a symbol mentioned
earlier in the conversation unless the latest message explicitly refers back to it (e.g. "iska",
"its", "same stock", "usi ka"). If the latest message names AXISBANK, fetch AXISBANK — never a
different, previously-discussed stock.
Call NO tools when the user only greets you, asks to explain a concept/feature, asks a "what is
X" definition question, or asks whether to buy/sell/hold (advice). Call tools when the user asks
for a price, market status, movers, or a company's announcements.
For index names (NIFTY 50, SENSEX, BANKNIFTY, FINNIFTY, NIFTY IT) use get_market_overview, NOT
get_stock_price. get_stock_price is only for individual company stocks (RELIANCE, TCS, etc.).
Call get_news for news/khabar about a stock or the market. Call get_sentiment for questions about
'sentiment', 'mahaul', or how a stock's news/mood looks."""

WRITER_SYSTEM = """You are StockSage AI, a friendly, respectful guide to the Indian stock market
and to the StockSage India app, created by Girish Gupta. Any live data needed has already been
fetched and is provided to you in the conversation — use it; you do not call tools yourself.

## Absolute rule — NO financial advice
NEVER give financial advice. Never recommend buying, selling, or holding any security. Never
give price targets, entry/exit points, stop-losses, sizing, or allocation. Never predict prices
or say a stock is "good"/"bad" to buy. If the user asks whether to buy/sell/hold or for a target
or recommendation, politely decline and suggest a SEBI-registered advisor.
Giving a price, index value, market data, news, or an explanation is NOT advice — provide the
requested information directly and completely.

## Portfolio (bookkeeping)
Recording a stock in the user's own portfolio is bookkeeping of THEIR decision, not advice.
If the data shows a "needs_confirmation" for a holding, do NOT say it is done — briefly restate
what they want to add (quantity, symbol, price) and ask them to confirm. If the data shows a
"need_info", politely ask for the missing symbol / quantity / average price.

## Grounding
The data provided to you is REAL, live data from our own systems. State the actual numbers
clearly and confidently. NEVER call it "simulated" or "not available" when data is given. If the
provided data shows an error or is empty, say so plainly instead of guessing. Do not invent
numbers.
Never reveal internal data providers, vendors, brokers, or APIs by name. If asked where the data
comes from, say it is sourced from the NSE and BSE exchanges.

## Language
Reply in the EXACT language and script the user used — English, Hindi (Devanagari), or Hinglish
(Roman-script Hindi/English mix). Mirror their code-mixing; if they switch, you switch.
CRITICAL — match the user's SCRIPT: if the user wrote in Roman/Latin letters (Hinglish, e.g.
"aaj market kaisa hai", "RELIANCE ka price"), you MUST reply in Roman/Latin letters (Hinglish) —
do NOT switch to Devanagari. Use Devanagari only if the user actually wrote in Devanagari.

## Concepts
For "what is X" / definition / concept questions, explain from your own knowledge — no live data
is needed. If the provided data is an error or empty, ignore it and answer from your knowledge.

## News & sentiment
When presenting news, list the headlines and name each item's source. When describing sentiment,
be NEUTRAL and informational (e.g. "recent coverage leans positive / negative / mixed", factoring
in the overall market trend and the stock's move) — it is a read on the mood, NEVER a buy/sell
recommendation. Add the usual not-advice reminder.

## Tone & respect (ALWAYS)
Always be polite, warm, and respectful. In Hindi/Hinglish ALWAYS address the user with the
respectful "आप"/"aap" form; NEVER use "तू/तुम/tu/tere". Even if the user is rude or abusive, stay
calm and gracious — never mirror it, never insult. Be concise and beginner-friendly. This is
educational information, not investment advice."""


# Referent pronouns that mean "the stock we were just talking about".
_REFERENT_RE = re.compile(
    r"\b(iska|iske|iski|isme|isko|isi|uska|uske|uski|usme|usi|inka|inke|its|same\s+stock)\b",
    re.IGNORECASE,
)

# Common Roman-script Hindi words → the message is Hinglish, not English.
_HINGLISH_RE = re.compile(
    r"\b(kya|hai|hain|kaisa|kaise|kaisi|kitna|kitne|kitni|mera|meri|mere|ka|ki|ke|ko|kar|karo|karna|"
    r"kardo|dikhao|dikha|batao|bata|bataye|le|lu|lo|liya|kharida|kharidu|becha|bhav|aaj|kal|abhi|nahi|"
    r"nahin|haan|kyun|acha|accha|theek|thik|paise|paisa|wala|wale|hoga|chahiye|chahta|dena|do|mujhe|"
    r"aap|aapka|aapke|apna|apne)\b",
    re.IGNORECASE,
)


def _detect_language(text: str) -> str:
    """Which language the writer should reply in, matching the user's message."""
    if re.search(r"[ऀ-ॿ]", text or ""):
        return "Hindi (Devanagari script)"
    if _HINGLISH_RE.search(text or ""):
        return "Hinglish (Roman-script Hindi/English mix)"
    return "English"


def _latest_user_text(history: List[Dict]) -> str:
    for m in reversed(history):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            return m["content"]
    return ""


def _writer_system_for(history: List[Dict]) -> str:
    lang = _detect_language(_latest_user_text(history))
    return (
        WRITER_SYSTEM
        + f"\n\n## Reply language (IMPORTANT)\nThe user wrote in {lang}. Reply ONLY in {lang}, "
        "matching their script exactly. Write cleanly with correct spelling; do NOT mix scripts, "
        "invent words, or garble spellings."
    )


def _router_history(history: List[Dict]) -> List[Dict]:
    """The router (fast 8B) anchors on old symbols if given the full history, so give it
    only the latest user message — unless that message uses a referent pronoun, in which
    case include the previous turn so 'iska/its' resolves to the right stock."""
    if not history:
        return history
    last = history[-1]
    text = last.get("content", "") if isinstance(last.get("content"), str) else ""
    if _REFERENT_RE.search(text):
        return history[-3:]  # prev user + prev assistant + current
    return [last]


async def _gather_tool_data(client, history: List[Dict], user_id=None) -> AsyncGenerator[Dict, None]:
    """Router phase (single round): the fast model's native function-calling picks the
    tools; we run them. Yields {'tool': name} events, then a final {'_data': [...]}."""
    today = datetime.now(_IST).date().isoformat()
    router_system = (
        ROUTER_SYSTEM
        + f"\nToday's date is {today} (IST). For get_price_on_date, pass the day and month; include "
        "the year ONLY if the user explicitly stated one (otherwise omit it)."
    )
    router_messages: List[Dict] = [{"role": "system", "content": router_system}] + _router_history(history)
    collected: List[Dict] = []
    try:
        resp = await client.chat.completions.create(
            model=NIM_MODEL_FAST, messages=router_messages, tools=TOOL_SCHEMAS,
            tool_choice="auto", max_tokens=300,
        )
    except Exception:
        logger.exception("router call failed")
        yield {"_data": collected}
        return

    seen = set()
    for tc in (resp.choices[0].message.tool_calls or []):
        key = (tc.function.name, tc.function.arguments)
        if key in seen:  # de-dupe identical parallel calls
            continue
        seen.add(key)
        yield {"type": "tool", "name": tc.function.name}
        result = await execute_tool(tc.function.name, tc.function.arguments or "{}", user_id)
        collected.append({"tool": tc.function.name, "result": result})

    yield {"_data": collected}


async def run_agent_stream(history: List[Dict], user_id=None) -> AsyncGenerator[Dict, None]:
    """Run one assistant turn. `history` is the running conversation (incl. the latest
    user message); the final assistant answer is appended in place. Yields WS events."""
    client = get_async_nim_client()

    # ── Phase 1: router gathers real data (reliable native tool calls) ──
    tool_data: List[Dict] = []
    try:
        async for ev in _gather_tool_data(client, history, user_id):
            if "_data" in ev:
                tool_data = ev["_data"]
            else:
                yield ev
    except Exception:
        logger.exception("router phase failed")  # fall through — writer can still answer

    # A portfolio write needs the user to confirm — surface the details to the UI.
    pending = next(
        (r["result"] for r in tool_data
         if isinstance(r.get("result"), dict) and r["result"].get("status") == "needs_confirmation"),
        None,
    )
    if pending:
        yield {"type": "confirm_request", "holding": {
            "symbol": pending["symbol"], "quantity": pending["quantity"], "avg_price": pending["avg_price"],
        }}

    # ── Phase 2: sarvam writes the final answer in the user's language ──
    # sarvam-m (Mistral-based) requires strict user/assistant alternation, so the
    # fetched data is merged into the last user turn rather than added as a new one.
    writer_messages: List[Dict] = [{"role": "system", "content": _writer_system_for(history)}] + [dict(m) for m in history]
    if tool_data:
        for i in range(len(writer_messages) - 1, -1, -1):
            if writer_messages[i]["role"] == "user":
                writer_messages[i]["content"] = (
                    f"{writer_messages[i]['content']}\n\n"
                    f"[real live data fetched for this question]:\n{json.dumps(tool_data)[:3800]}\n"
                    "Use ONLY this real data for any figures."
                )
                break

    try:
        stream = await client.chat.completions.create(
            model=NIM_MODEL, messages=writer_messages, stream=True,
            max_tokens=800, extra_body=WRITER_EXTRA_BODY,
        )
    except Exception:
        logger.exception("writer phase failed")
        yield {"type": "error", "detail": "The assistant is unavailable right now. Please try again."}
        return

    answer = ""
    async for chunk in stream:
        if not chunk.choices:
            continue
        piece = chunk.choices[0].delta.content
        if piece:
            answer += piece
            yield {"type": "token", "text": piece}

    if not answer.strip():
        yield {"type": "token", "text": _EMPTY_FALLBACK}
        answer = _EMPTY_FALLBACK

    history.append({"role": "assistant", "content": answer})
    yield {"type": "done"}


async def _stream_writer(history, instruction, stored_user_turn):
    """Stream a sarvam reply for a synthetic instruction (confirm/cancel results). Stores a
    clean user turn + the assistant answer so history alternation stays valid."""
    client = get_async_nim_client()
    messages = [{"role": "system", "content": _writer_system_for(history)}] + history + [{"role": "user", "content": instruction}]
    try:
        stream = await client.chat.completions.create(
            model=NIM_MODEL, messages=messages, stream=True, max_tokens=300, extra_body=WRITER_EXTRA_BODY,
        )
    except Exception:
        logger.exception("confirm/cancel writer failed")
        yield {"type": "error", "detail": "Something went wrong. Please try again."}
        return
    answer = ""
    async for chunk in stream:
        if not chunk.choices:
            continue
        piece = chunk.choices[0].delta.content
        if piece:
            answer += piece
            yield {"type": "token", "text": piece}
    history.append({"role": "user", "content": stored_user_turn})
    history.append({"role": "assistant", "content": answer or "Done."})
    yield {"type": "done"}


async def run_confirm_holding(history, holding, user_id):
    """Execute the confirmed portfolio write, then confirm to the user in their language."""
    import asyncio
    from services import portfolio_actions as pa

    if not user_id:
        yield {"type": "token", "text": "Please sign in to modify your portfolio."}
        yield {"type": "done"}
        return

    result = await asyncio.to_thread(
        pa.record_equity_holding, user_id, holding.get("symbol"),
        holding.get("quantity"), holding.get("avg_price"),
    )
    sym, qty, price = holding.get("symbol"), holding.get("quantity"), holding.get("avg_price")
    if result.get("ok"):
        instruction = (
            f"[system] I have successfully RECORDED {qty} shares of {sym} at an average price of "
            f"₹{price} in the user's portfolio (bookkeeping done). Confirm to the user in ONE short, "
            "friendly sentence in their language that it is added, and remind them it is bookkeeping, not advice."
        )
    else:
        instruction = (
            "[system] Recording the holding FAILED due to a system error. Apologize briefly in the "
            "user's language and ask them to try again."
        )
    async for ev in _stream_writer(history, instruction, f"Confirmed: add {qty} {sym} at {price}"):
        yield ev


async def run_cancel_holding(history):
    """Acknowledge that the user cancelled the portfolio add."""
    instruction = (
        "[system] The user cancelled adding the holding to their portfolio. Acknowledge briefly and "
        "politely in their language that no problem, nothing was added."
    )
    async for ev in _stream_writer(history, instruction, "Cancelled adding the holding."):
        yield ev
