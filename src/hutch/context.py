"""Context sizing, the pre-run warning (LM-3) and the needle-at-the-top self-check (LM-2).

The failure all three exist for: a local model quietly dropping the START of the prompt - which is where the
system prompt and tool definitions live - and then behaving as if it had never been told what it is or what it
may call. Nothing errors. So Hutch (1) always requests a window it computed (LM-1), (2) refuses to start a run
whose prompt + tools cannot fit (LM-3), and (3) proves, once per model + window, that a fact placed at the very
top of a long prompt is still recalled (LM-2), failing loudly if not.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from typing import Any, Optional

from .fit import Fit, estimate_fit
from .hardware import Hardware
from .providers.base import ChatRequest, ModelMeta, Provider, ProviderError

CHARS_PER_TOKEN = 3.2          # deliberately conservative: code/JSON tokenise denser than prose
PER_MESSAGE_OVERHEAD = 6
WARN_AT = 0.60                 # share of the usable window consumed before the first step
FAIL_AT = 1.00


def estimate_tokens(text: str) -> int:
    return int(math.ceil(len(text) / CHARS_PER_TOKEN))


#: a conservative per-image estimate for prompt budgeting; vision tokenisation is vendor-specific and
#: exact counts come back from the provider in usage. Images are counted so they are never free.
IMAGE_TOKEN_ESTIMATE = 800


def _content_tokens(content: Any) -> int:
    """Estimate one message body: text by chars, image parts by a flat conservative block."""
    if isinstance(content, str):
        return estimate_tokens(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "image_url":
                    total += IMAGE_TOKEN_ESTIMATE
                elif part.get("type") == "text":
                    total += estimate_tokens(str(part.get("text") or ""))
                else:
                    total += estimate_tokens(json.dumps(part)[:2000])
        return total
    return estimate_tokens(str(content or ""))


def prompt_tokens(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> tuple[int, int]:
    """(message tokens, tool-definition tokens). Tool schemas are sent with every request."""
    msg = sum(_content_tokens(m.get("content")) + PER_MESSAGE_OVERHEAD
              + sum(estimate_tokens(json.dumps(tc)) for tc in (m.get("tool_calls") or [])) for m in messages)
    tool = estimate_tokens(json.dumps(tools, separators=(",", ":"))) if tools else 0
    return msg, tool


@dataclass
class PromptCheck:
    severity: str              # ok | warn | fail
    message_tokens: int
    tool_tokens: int
    reserve_tokens: int
    effective_ctx: int
    message: str
    fix: str = ""

    @property
    def used(self) -> int:
        return self.message_tokens + self.tool_tokens

    @property
    def share(self) -> float:
        room = max(1, self.effective_ctx - self.reserve_tokens)
        return self.used / room


def check_prompt(messages: list[dict[str, Any]], tools: list[dict[str, Any]], effective_ctx: int,
                 max_turn_tokens: int) -> PromptCheck:
    """LM-3: warn before a run when prompt + tools exceed (or crowd) the window the model will actually get."""
    mt, tt = prompt_tokens(messages, tools)
    c = PromptCheck("ok", mt, tt, max_turn_tokens, effective_ctx, "")
    pct = c.share * 100
    if c.share >= FAIL_AT:
        c.severity = "fail"
        c.message = (f"the prompt ({mt:,} tokens) plus {len(tools)} tool definition(s) ({tt:,} tokens) cannot fit "
                     f"the {effective_ctx:,}-token window once {max_turn_tokens:,} tokens are reserved for the reply")
        c.fix = ("use a model/hardware with a larger window, give the bot fewer tools (default is 8 or fewer), "
                 "or shorten its instructions and memory")
    elif c.share >= WARN_AT:
        c.severity = "warn"
        c.message = (f"the prompt and tools already use {pct:.0f}% of the {effective_ctx:,}-token window before the "
                     "first step; later steps will crowd it and the model may lose earlier context")
        c.fix = "give the bot fewer tools, trim its instructions, or pick a model with a larger window"
    else:
        c.message = f"prompt and tools use {pct:.0f}% of the {effective_ctx:,}-token window"
    return c


@dataclass
class ContextPlan:
    num_ctx: Optional[int]     # None for hosted models
    fit: Optional[Fit]
    blocked: bool
    note: str


def plan_context(meta: Optional[ModelMeta], hw: Hardware, want: int, min_ctx: int, *, local: bool) -> ContextPlan:
    """Decide the window to REQUEST (LM-1). Always explicit for local models; hosted models size themselves."""
    if not local:
        return ContextPlan(None, None, False, "hosted model: the provider manages the window")
    if meta is None:
        return ContextPlan(want, None, False, f"model metadata unavailable; requesting {want:,} tokens unverified")
    fit = estimate_fit(meta, hw, want, min_ctx=min_ctx)
    if fit.status == "wont_fit":
        return ContextPlan(max(fit.effective_ctx, 0) or None, fit, True, fit.reason)
    return ContextPlan(fit.effective_ctx, fit, False, fit.reason)


# ----------------------------------------------------------------- self-check (LM-2)

_WORDS = ("amber birch cobalt dune ember fjord garnet harbor indigo juniper kelp lagoon meadow nectar opal "
          "pine quartz ridge sable tundra umber velvet willow yarrow zephyr").split()


@dataclass
class SelfCheck:
    ok: bool
    detail: str
    prompt_tokens: int = 0
    num_ctx: int = 0
    seconds: float = 0.0
    truncated: bool = False
    recalled: str = ""
    error_kind: str = ""

    def to_json(self) -> str:
        return json.dumps(self.__dict__)


def _filler(target_tokens: int, rng: random.Random) -> str:
    out, n = [], 0
    while n < target_tokens:
        s = (f"Log entry {rng.randint(1000, 9999)}: the {rng.choice(_WORDS)} {rng.choice(_WORDS)} reported "
             f"{rng.randint(1, 99)} items near the {rng.choice(_WORDS)} station.")
        out.append(s)
        n += estimate_tokens(s) + 1
    return " ".join(out)


def run_selfcheck(provider: Provider, model: str, num_ctx: int, *, size_tokens: Optional[int] = None,
                  seed: Optional[int] = None) -> SelfCheck:
    """Place a code word at the very top of a long prompt and ask for it back.

    ``size_tokens`` defaults to 80% of the window, capped at 12k so a CPU-only machine is not stuck for an hour;
    anything past the runtime's default window (4k) is enough to expose a window that was not applied.
    """
    rng = random.Random(seed)
    code = f"{rng.choice(_WORDS).upper()}-{rng.randint(1000, 9999)}-{rng.choice(_WORDS).upper()}"
    size = size_tokens or min(int(num_ctx * 0.8), 12_000)
    size = max(256, min(size, int(num_ctx * 0.9)))
    needle = f"IMPORTANT: the secret code word for this check is {code}. Remember it exactly."
    question = "What was the secret code word stated at the very beginning? Reply with only the code word."
    messages = [{"role": "user", "content": needle + "\n\n" + _filler(size, rng) + "\n\n" + question}]
    t0 = time.perf_counter()
    try:
        res = provider.chat(ChatRequest(model=model, messages=messages, num_ctx=num_ctx, max_tokens=64,
                                        think=False, temperature=0.0, keep_alive="10m"))
    except ProviderError as exc:
        return SelfCheck(False, f"the model call failed: {exc}", num_ctx=num_ctx, error_kind=exc.kind,
                         seconds=time.perf_counter() - t0)
    secs = time.perf_counter() - t0
    recalled = code in (res.content or "").upper() or code.lower() in (res.content or "").lower()
    if recalled:
        return SelfCheck(True, f"recalled the code word from the top of a ~{size:,}-token prompt in a "
                               f"{num_ctx:,}-token window", res.prompt_tokens, num_ctx, secs, res.prompt_truncated,
                         (res.content or "").strip()[:80])
    why = ("the runtime truncated the prompt from the front (the window was not applied or is too small)"
           if res.prompt_truncated else
           "the model did not recall it although the prompt was not reported truncated: it is weak at long "
           "context at this size, or the window is silently smaller than requested")
    return SelfCheck(False, f"could NOT recall the code word - {why}", res.prompt_tokens, num_ctx, secs,
                     res.prompt_truncated, (res.content or "").strip()[:80])
