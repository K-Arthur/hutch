"""Built-in agent loop - Hutch's own runtime, now over the provider layer.

The loop is deliberately thin; what it adds over a bare tool-calling loop is every guard the research said real
products lack:

 context    an explicit window for local models, a pre-run check that prompt + tools fit (LM-1, LM-3), a self-check
            that the window really works (LM-2), cold loads as a visible state (LM-6)
 tools      parse -> coerce -> validate -> one retry with the error (LM-13); the same call 3x is a loop, not
            executed (SR-5); output truncated per tool with the full text kept as an artifact (PF-2)
 models     availability failures fall back in order (SR-8); quality failures escalate ONE rung (LM-9); every hosted
            hop passes the spend guard and, for a local-default bot, asks first (LM-10, SR-2)
 accounting exact tokens, cost, cache reads, context use and a model/tool/Hutch time split per step (SR-2, PF-11);
            the system prompt and tool list are frozen for the whole run so provider caches hit (PF-1)
 stop       an in-flight model call is aborted by closing its socket, so Stop never waits for the model (UI-2)
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..approvals import DeniedError
from ..context import check_prompt, plan_context, prompt_tokens as estimate_prompt_tokens, run_selfcheck
from ..hardware import Hardware, probe
from ..models import Event, EventType, Run, RunStatus
from ..providers import ChatRequest, Provider, ProviderError
from ..providers.base import ModelMeta
from ..providers.pricing import PriceBook
from ..safety import Decision, Verdict
from ..tools import Tool, ToolContext
from .base import RunAborted
from ..connections import ConnectionBook
from ..health import record_outcome
from ..providers.connection import provider_for_connection
from .ladder import Ladder, Rung, SpendGuard, get_provider
from .steps import StepTimer, call_tool, finish_step
from .toolrepair import LoopDetector, coerce_args, repair_instruction, unknown_tool_message, validate_args

SYSTEM_TEMPLATE = """You are {name}, a bot running on hutch - a local, human-supervised agent platform.

Your purpose: {description}

Operator instructions:
{instructions}

Rules of engagement:
- Your entire world is your workspace directory: {workspace}. File reads/writes stay inside it.
- Tool calls that mutate anything may require human approval; the run pauses until a human answers. If an action is denied, do not retry it - adapt or report.
- Prefer the fewest tool calls that accomplish the task. Never repeat a call that already returned what you need.
- When you are done, reply with a concise summary of what you did, created, or found. If you could not finish, say exactly what blocked you.
{rehearsal}
Current date: {date} (UTC)
{memory_block}"""

REHEARSAL_NOTE = ("- This is a REHEARSAL (dry run): actions that would change anything are simulated and logged, "
                  "not executed. Carry on as if they succeeded and describe what you would do.\n")

DEFAULT_LOCAL_TURN_TOKENS = 2048     # SR-5: a small model rambling for 30k tokens is a failure, not an answer
DEFAULT_HOSTED_TURN_TOKENS = 16000   # hosted models think inside max_tokens; a low cap truncates mid-thought
DEFAULT_WANT_CTX = 16384
MAX_MALFORMED_STREAK = 4             # without an escalation target, give up after this many bad turns
RATE_LIMIT_PAUSE_MAX = 30.0


_CONN_PROVIDERS: dict[tuple, Provider] = {}


def reset_connection_cache() -> None:
    _CONN_PROVIDERS.clear()


@dataclass
class Session:
    rung: Rung
    provider: Provider
    num_ctx: Optional[int]
    meta: Optional[ModelMeta]


class BuiltinRuntime:
    kind = "builtin"

    def __init__(self, *, hardware: Optional[Hardware] = None, prices: Optional[PriceBook] = None,
                 provider_factory: Optional[Callable[[str, Optional[str]], Provider]] = None,
                 sleep: Callable[[float], None] = time.sleep):
        self._hw = hardware
        self._prices = prices
        self._factory = provider_factory or get_provider
        self._sleep = sleep

    # ------------------------------------------------------------------ prompt

    def _system_prompt(self, ctx: ToolContext) -> str:
        import datetime as dt
        facts = ctx.store.recall_all(ctx.bot.id) if ctx.bot.memory_enabled else []
        memory_block = ""
        if facts:
            joined = "\n".join(f"- {m.key}: {m.value}" for m in facts[:40])
            memory_block = "What you remember from previous runs:\n" + joined
        return SYSTEM_TEMPLATE.format(
            name=ctx.bot.name, description=ctx.bot.description or "(none given)",
            instructions=ctx.bot.instructions or "(none given)", workspace=ctx.workspace,
            rehearsal=REHEARSAL_NOTE if ctx.dry_run else "",
            date=dt.datetime.now(dt.timezone.utc).date().isoformat(), memory_block=memory_block)

    # --------------------------------------------------------------- helpers

    def _hardware(self) -> Hardware:
        if self._hw is None:
            self._hw = probe(with_runtimes=False)
        return self._hw

    def _connections(self, ctx: ToolContext) -> ConnectionBook:
        return ConnectionBook(ctx.config.state_dir)

    def _prices_for(self, ctx: ToolContext) -> PriceBook:
        if self._prices is None:
            self._prices = PriceBook(ctx.config.state_dir / "prices.json")
        self._prices.flat_providers = self._connections(ctx).flat_providers()
        return self._prices

    def _provider_for(self, ctx: ToolContext, ladder: Ladder, rung: Rung) -> Provider:
        """A configured Connection wins over a built-in provider name; its terms must be acknowledged first."""
        book = self._connections(ctx)
        conn = book.get(rung.provider)
        if conn is None:
            return self._factory(rung.provider, ladder.base_url_for(rung))
        status = book.ack_status(ctx.store, rung.provider)
        if status in ("required", "stale"):
            raise ProviderError(
                "auth", f"the terms of '{conn.title}' have not been acknowledged{' (they changed)' if status == 'stale' else ''}: "
                        f"read them on the Connections page and acknowledge, or run `hutch connections ack {conn.name}`",
                provider=conn.name)
        key = (rung.provider, rung.model, conn.base_url, conn.protocol, str(sorted(conn.model_protocols.items())),
               book.key(conn.name) is not None)
        cached = _CONN_PROVIDERS.get(key)
        if cached is None:
            cached = _CONN_PROVIDERS[key] = provider_for_connection(book, conn.name, rung.model)
        return cached

    @staticmethod
    def _log(ctx: ToolContext, run: Run, kind: str, note: str, **extra: Any) -> None:
        ctx.emit(Event(run_id=run.id, type=EventType.log, data={"kind": kind, "note": note, **extra}))

    @staticmethod
    def _turn_cap(bot, rung: Rung) -> int:
        return bot.limits.max_turn_tokens or (DEFAULT_LOCAL_TURN_TOKENS if rung.local else DEFAULT_HOSTED_TURN_TOKENS)

    @staticmethod
    def _register_cancel(ctx: ToolContext):
        def register(fn):
            ctx.cancel_hooks.append(fn)

            def unregister():
                try:
                    ctx.cancel_hooks.remove(fn)
                except ValueError:
                    pass
            return unregister
        return register

    @staticmethod
    def _set_status(ctx: ToolContext, run: Run, status: RunStatus, model: str) -> None:
        run.status = status
        run.model_used = model
        ctx.store.update_run(run)
        ctx.emit(Event(run_id=run.id, type=EventType.status, data={"status": status.value, "model": model}))

    def _interruptible_sleep(self, seconds: float, stop: Callable[[], bool]) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end and not stop():
            self._sleep(min(0.25, max(0.0, end - time.monotonic())))

    # ----------------------------------------------------------- bring online

    def _bring_online(self, ctx: ToolContext, run: Run, ladder: Ladder, rung: Rung, messages: list[dict],
                      specs: list[dict]) -> Session:
        """Make a rung ready: window, pre-run check, cold load, self-check. Raises ProviderError on failure."""
        bot = ctx.bot
        provider = self._provider_for(ctx, ladder, rung)
        if not rung.local:
            return Session(rung, provider, None, None)
        meta = provider.show(rung.model) if rung.provider == "ollama" else None
        num_ctx: Optional[int] = None
        if rung.provider == "ollama":
            if meta is None:
                health = provider.health()
                if not health.ok:
                    raise ProviderError("unreachable", f"{health.detail}", provider="ollama")
                raise ProviderError("model_missing", f"model '{rung.model}' is not installed - "
                                                     f"`ollama pull {rung.model}`", provider="ollama")
            from ..presets import load_presets
            preset = load_presets(ctx.config.state_dir / "presets.json").get(bot.preset or "")
            want = bot.num_ctx or (preset.want_ctx if preset else DEFAULT_WANT_CTX)
            floor = min(want, preset.min_ctx if preset else 4096)
            plan = plan_context(meta, self._hardware(), want, floor, local=True)
            if plan.blocked or not plan.num_ctx:
                raise ProviderError("oom", f"{rung.spec} does not fit this machine: {plan.note}", provider="ollama")
            num_ctx = plan.num_ctx
            self._log(ctx, run, "context", f"{rung.model}: requesting a {num_ctx:,}-token window ({plan.note})",
                      num_ctx=num_ctx, fit=plan.fit.status if plan.fit else "unknown",
                      estimated=bool(plan.fit and plan.fit.estimated))
        # LM-3: prompt + tools vs the window the model will actually get
        if num_ctx:
            chk = check_prompt(messages, specs, num_ctx, self._turn_cap(bot, rung))
            if chk.severity != "ok":
                self._log(ctx, run, "context", f"{chk.severity}: {chk.message}. {chk.fix}", severity=chk.severity)
            if chk.severity == "fail":
                raise ProviderError("context", f"{chk.message}. {chk.fix}", provider=rung.provider)
        # LM-6: a cold load is a visible state, not a mystery pause
        if rung.provider == "ollama" and hasattr(provider, "is_loaded") and not provider.is_loaded(rung.model):
            self._set_status(ctx, run, RunStatus.loading_model, rung.spec)
            try:
                ms = provider.preload(rung.model, "10m")
            finally:
                self._set_status(ctx, run, RunStatus.running, rung.spec)
            ctx.store.kv_set(f"model_load:{rung.model}", json.dumps({"ms": ms, "at": time.time()}))
            self._log(ctx, run, "load", f"loaded {rung.model} into memory in {ms / 1000:.1f}s (cold load)", load_ms=ms)
        # LM-2: prove the window works, once per model build + window
        if bot.selfcheck and num_ctx and rung.provider == "ollama":
            key = f"selfcheck:{meta.digest or rung.model}:{rung.model}:{num_ctx}:{meta.template_hash}"
            cached = ctx.store.kv_get(key)
            sc = json.loads(cached) if cached else None
            if sc is None:
                self._log(ctx, run, "selfcheck", f"checking that {rung.model} really recalls a fact placed at the "
                                                 f"top of a long prompt in a {num_ctx:,}-token window...")
                res = run_selfcheck(provider, rung.model, num_ctx)
                sc = res.__dict__
                if res.ok:
                    ctx.store.kv_set(key, json.dumps(sc))
            if not sc.get("ok"):
                self._log(ctx, run, "selfcheck", f"FAILED: {sc.get('detail')}", ok=False)
                raise ProviderError("context", f"context self-check failed for {rung.spec}: {sc.get('detail')}",
                                    provider="ollama")
            self._log(ctx, run, "selfcheck", f"passed: {sc.get('detail')}", ok=True)
        return Session(rung, provider, num_ctx, meta)

    # -------------------------------------------------------------- switching

    def _ask_first_hosted(self, ctx: ToolContext, ladder: Ladder, rung: Rung, why: str, est_prompt: int) -> None:
        """LM-10: a bot that is local by default asks before its FIRST hosted call (even in auto mode)."""
        if not (ladder.local_default and not rung.local):
            return
        worst = self._prices_for(ctx).cost(rung.provider, rung.model, est_prompt, self._turn_cap(ctx.bot, rung))
        decision = Decision(Verdict.ask, f"call hosted model {rung.spec}", "escalate:hosted",
                            rule="ask:hosted-call", risk="medium")
        ctx.gate.decide(
            "escalation", f"send this run to the hosted model {rung.spec} ({why})",
            {"model": rung.spec, "reason": why, "worst_case_next_call_usd": worst,
             "what_is_sent": "the conversation so far, including tool results, goes to the model provider"},
            decision, ask_in_auto=True)

    def _switch(self, ctx, run, ladder: Ladder, guard: SpendGuard, rung: Rung, why: str, kind: str, messages,
                specs, est_prompt: int) -> Optional[Session]:
        """Move to ``rung`` (fallback or escalation) if the guards allow; None if they do not.

        A refusal sticks for the rest of the run: a human who said no, a cap that is already reached, or a model
        that would not start are never asked about / tried again on every later bad turn.
        """
        if rung.spec in ladder.blocked or (ladder.hosted_denied and not rung.local):
            return None
        refusal = guard.refusal(rung, est_prompt, self._turn_cap(ctx.bot, rung))
        if refusal:
            ladder.blocked.add(rung.spec)
            self._log(ctx, run, kind, f"cannot {kind} to {rung.spec}: {refusal}", blocked=True)
            return None
        try:
            self._ask_first_hosted(ctx, ladder, rung, why, est_prompt)
        except DeniedError as exc:
            ladder.hosted_denied = True
            self._log(ctx, run, kind, f"{kind} to {rung.spec} was not approved: {exc}", blocked=True)
            return None
        try:
            session = self._bring_online(ctx, run, ladder, rung, messages, specs)
        except ProviderError as exc:
            ladder.blocked.add(rung.spec)
            self._log(ctx, run, kind, f"{rung.spec} is not usable either: {exc}", blocked=True)
            return None
        prev = ladder.current
        ladder.current = rung
        run.model_used = rung.spec
        self._log(ctx, run, kind, f"{kind}: {prev.spec} -> {rung.spec} ({why})",
                  from_model=prev.spec, to_model=rung.spec, reason=why, hosted=not rung.local)
        return session

    def _recover(self, ctx, run, ladder: Ladder, guard: SpendGuard, exc: ProviderError, messages, specs,
                 est_prompt: int) -> Optional[Session]:
        """A model call failed: escalate on a quality failure, fall back on an availability failure."""
        bot = ctx.bot
        if exc.kind == "context":
            esc = ladder.next_escalation()
            if esc and bot.escalation and bot.escalation.on_context_overflow:
                return self._switch(ctx, run, ladder, guard, esc, f"context overflow: {exc}", "escalation", messages,
                                    specs, est_prompt)
            return None
        if exc.retryable or exc.kind in ("model_missing", "auth"):
            nxt = ladder.next_fallback()
            if nxt is not None:
                return self._switch(ctx, run, ladder, guard, nxt, str(exc), "fallback", messages, specs, est_prompt)
        return None

    # ---------------------------------------------------------------- startup

    def _start(self, ctx, run, ladder: Ladder, guard: SpendGuard, messages, specs, stop, est_prompt: int) -> Session:
        """Bring up the primary model; walk the fallback chain if it is unavailable (SR-8)."""
        rung = ladder.primary
        while True:
            ladder.current = rung
            try:
                refusal = guard.refusal(rung, est_prompt, self._turn_cap(ctx.bot, rung))
                if refusal:
                    capped = ProviderError("other", refusal, provider=rung.provider)
                    capped.cost_cap = True  # type: ignore[attr-defined]
                    raise capped
                if rung is not ladder.primary:
                    self._ask_first_hosted(ctx, ladder, rung, "the primary model is unavailable", est_prompt)
                session = self._bring_online(ctx, run, ladder, rung, messages, specs)
                self._announce_plan(ctx, run, session, est_prompt)
                return session
            except DeniedError as denied:
                raise RunAborted("error", f"the hosted fallback {rung.spec} was not approved: {denied}") from denied
            except ProviderError as exc:
                if stop():
                    raise RunAborted("stopped", "user requested stop") from exc
                nxt = ladder.next_fallback()
                if nxt is None:
                    raise RunAborted(_exit_reason(exc), f"cannot start on {rung.spec}: {exc}") from exc
                self._log(ctx, run, "fallback", f"{rung.spec} is unavailable ({exc}); trying {nxt.spec}",
                          from_model=rung.spec, to_model=nxt.spec, reason=str(exc))
                rung = nxt

    def _announce_plan(self, ctx, run, session: Session, est_prompt: int) -> None:
        """SR-2: what this run may cost, visible in the transcript before the first model call."""
        cap = self._turn_cap(ctx.bot, session.rung)
        ceiling = self._prices_for(ctx).estimate_run_ceiling(session.rung.provider, session.rung.model, est_prompt,
                                                             cap, ctx.bot.limits.max_steps)
        run.context_limit = session.num_ctx or 0
        run.model_used = session.rung.spec
        ctx.store.update_run(run)
        cost_note = (f", worst case ${ceiling:.2f}" if ceiling else ", no per-token cost" if session.rung.local
                     else ", price unknown")
        self._log(ctx, run, "plan", f"{session.rung.spec}: ~{est_prompt:,} prompt tokens, up to "
                                    f"{ctx.bot.limits.max_steps} steps{cost_note}",
                  model=session.rung.spec, window=session.num_ctx, worst_case_usd=ceiling, prompt_tokens=est_prompt)

    # -------------------------------------------------------------------- loop

    def execute(self, run: Run, ctx: ToolContext, tools: dict[str, Tool], stop: Callable[[], bool]) -> str:
        bot = ctx.bot
        ladder = Ladder(bot)
        prices = self._prices_for(ctx)
        guard = SpendGuard(ctx.store, bot, run, prices, self._connections(ctx))
        system = self._system_prompt(ctx)
        specs = [tools[n].spec() for n in sorted(tools)]             # PF-1 / PF-3: frozen, deterministic, allowed only
        prefix_hash = hashlib.sha256((system + json.dumps(specs, sort_keys=True)).encode()).hexdigest()[:12]
        messages: list[dict[str, Any]] = [{"role": "system", "content": system},
                                          {"role": "user", "content": run.prompt}]
        mt, tt = estimate_prompt_tokens(messages, specs)
        est_prompt = mt + tt
        run.model_used = ladder.primary.spec

        session = self._start(ctx, run, ladder, guard, messages, specs, stop, est_prompt)
        loop = LoopDetector()
        malformed_streak = loop_strikes = 0
        rate_limited_once = False
        warned_quota: set[str] = set()

        while True:
            if stop():
                raise RunAborted("stopped", "user requested stop")
            if run.steps >= bot.limits.max_steps:
                raise RunAborted("steps_exceeded", f"hit max_steps={bot.limits.max_steps}")
            if ctx.store.tokens_today(bot.id) > bot.limits.daily_token_cap:
                raise RunAborted("token_cap", f"daily cap {bot.limits.daily_token_cap} exceeded")
            refusal = guard.refusal(session.rung, est_prompt, self._turn_cap(bot, session.rung))
            if refusal:
                raise RunAborted("cost_cap", refusal)

            quota = guard.quota_state(session.rung)
            if quota and quota[1] and quota[0] / quota[1] >= (self._connections(ctx).get(session.rung.provider).quota.warn_at) \
                    and session.rung.provider not in warned_quota:
                warned_quota.add(session.rung.provider)
                self._log(ctx, run, "quota", f"{session.rung.provider}: {quota[0]:,} of {quota[1]:,} allowance tokens "
                                             f"used in the {quota[2]} window ({quota[0] / quota[1] * 100:.0f}%)",
                          used=quota[0], limit=quota[1])

            timer = StepTimer()
            req = ChatRequest(
                model=session.rung.model, messages=messages, tools=specs, num_ctx=session.num_ctx,
                max_tokens=self._turn_cap(bot, session.rung), think=bot.think if bot.think is not None else False,
                register_cancel=self._register_cancel(ctx), is_cancelled=stop, session_id=run.id,
                keep_alive="30m" if _keep_resident(ctx, bot) else "10m")
            t_call = time.perf_counter()
            try:
                result = session.provider.chat(req)
                record_outcome(ctx.store, session.rung.provider, True)
            except ProviderError as exc:
                if stop():
                    raise RunAborted("stopped", "user requested stop") from exc
                record_outcome(ctx.store, session.rung.provider, False, f"{exc.kind}: {exc}")
                if (exc.kind == "rate_limit" and not rate_limited_once
                        and (exc.retry_after or 5.0) <= RATE_LIMIT_PAUSE_MAX):
                    rate_limited_once = True
                    wait = exc.retry_after or 5.0
                    self._log(ctx, run, "retry", f"{session.rung.spec} rate-limited; waiting {wait:.0f}s then retrying once")
                    self._interruptible_sleep(wait, stop)
                    continue
                nxt = self._recover(ctx, run, ladder, guard, exc, messages, specs, est_prompt)
                if nxt is None:
                    raise RunAborted(_exit_reason(exc), f"model call failed ({session.rung.spec}): {exc}") from exc
                session, rate_limited_once = nxt, False
                continue
            rate_limited_once = False
            timer.model(time.perf_counter() - t_call)

            # ---- exact accounting (SR-2)
            run.steps += 1
            run.tokens += result.prompt_tokens + result.completion_tokens
            run.context_used, run.context_limit = result.prompt_tokens, session.num_ctx or run.context_limit
            cost = prices.cost(session.rung.provider, session.rung.model, result.prompt_tokens,
                               result.completion_tokens, result.cached_tokens, result.cache_write_tokens)
            for note in result.notes:
                self._log(ctx, run, "stream_retry" if "without streaming" in note else "note", note)
            if result.content and result.tool_calls:
                ctx.emit(Event(run_id=run.id, type=EventType.message,
                               data={"role": "assistant", "content": result.content}))
            extra: dict[str, Any] = {}
            if result.load_ms:
                extra["load_ms"] = round(result.load_ms)
            if result.tokens_per_sec:
                extra["tok_s"] = round(result.tokens_per_sec, 1)
            finish_step(run, ctx, timer, model=session.rung.spec, prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens, cached_tokens=result.cached_tokens,
                        cost_usd=cost or 0.0, prefix=prefix_hash, window=session.num_ctx or 0,
                        finish=result.finish_reason, streamed=result.streamed, **extra)
            # ---- context overflow is a quality failure (LM-9): the model lost the start of its prompt
            if result.prompt_truncated:
                self._log(ctx, run, "context", "the runtime truncated the prompt: " + "; ".join(result.notes))
                esc = ladder.next_escalation()
                nxt = (self._switch(ctx, run, ladder, guard, esc, "context overflow", "escalation", messages, specs,
                                    est_prompt)
                       if esc and bot.escalation and bot.escalation.on_context_overflow else None)
                if nxt is None:
                    raise RunAborted("context", "the prompt no longer fits the model's window and was truncated from "
                                                "the front, so it lost its instructions; use a model with a larger "
                                                "window or give the bot fewer tools")
                session = nxt
                continue

            # ---- final answer
            if not result.tool_calls:
                final = result.content or ""
                ctx.emit(Event(run_id=run.id, type=EventType.message, data={"role": "assistant", "content": final}))
                return final

            # a hard spend cap stops FURTHER spending; it never discards a final answer already paid for
            if bot.limits.max_cost_usd and run.cost_usd >= bot.limits.max_cost_usd:
                raise RunAborted("cost_cap", f"run spend ${run.cost_usd:.4f} reached its "
                                             f"${bot.limits.max_cost_usd:.2f} cap")
            if result.finish_reason == "length":
                self._log(ctx, run, "note", f"the reply hit the per-turn cap of {self._turn_cap(bot, session.rung)} tokens")

            messages.append({"role": "assistant", "content": result.content or "", "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.name,
                              "arguments": tc.raw if (tc.parse_error and tc.raw) else json.dumps(tc.arguments)}}
                for tc in result.tool_calls]})
            turn_bad = loop_hit = False
            for tc in result.tool_calls:
                tool = tools.get(tc.name)
                args, problems = tc.arguments, []
                if tool is None:
                    problems = [unknown_tool_message(tc.name, list(tools))]
                elif tc.parse_error:
                    problems = [tc.parse_error]
                else:
                    args, changed = coerce_args(tool.parameters, args)
                    if changed:
                        self._log(ctx, run, "repair", f"repaired {tc.name} arguments ({'; '.join(changed)})")
                    problems = validate_args(tool.parameters, args)
                if problems:
                    turn_bad = True
                    msg = problems[0] if tool is None else repair_instruction(tc.name, problems, tool.parameters)
                    ctx.emit(Event(run_id=run.id, type=EventType.tool_call, data={"tool": tc.name, "args": args}))
                    ctx.emit(Event(run_id=run.id, type=EventType.tool_result,
                                   data={"tool": tc.name, "ok": False, "output": f"rejected: {msg}"}))
                    self._log(ctx, run, "repair", f"malformed call to {tc.name}: {'; '.join(problems)}")
                    messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": msg})
                    continue
                if loop.check(tc.name, args):
                    loop_hit = True
                    loop_strikes += 1
                    note = (f"You have made this exact call to `{tc.name}` repeatedly. It was NOT run again. "
                            "Use what you already have, try a different approach, or finish and report what blocked you.")
                    ctx.emit(Event(run_id=run.id, type=EventType.tool_call, data={"tool": tc.name, "args": args}))
                    ctx.emit(Event(run_id=run.id, type=EventType.tool_result,
                                   data={"tool": tc.name, "ok": False, "output": note}))
                    self._log(ctx, run, "loop", f"loop detected: {tc.name} called with identical arguments 3 times "
                                                "(not executed again)", tool=tc.name)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": note})
                    continue
                if stop():
                    raise RunAborted("stopped", "user requested stop")
                tool_timer = StepTimer()
                res = call_tool(run, ctx, tools, tc.name, args, tool_timer)
                run.tool_ms += tool_timer.tool_ms
                messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name,
                                 "content": res.output or "(empty)"})

            malformed_streak = malformed_streak + 1 if turn_bad else 0
            if loop_hit and loop_strikes >= 2:
                esc = ladder.next_escalation()
                nxt = (self._switch(ctx, run, ladder, guard, esc, "the model keeps repeating the same call",
                                    "escalation", messages, specs, est_prompt)
                       if esc and bot.escalation and bot.escalation.on_loop else None)
                if nxt is None:
                    raise RunAborted("loop", "the bot called the same tool with the same arguments again after being "
                                             "told it would not run; no escalation model is configured")
                session, loop_strikes, loop = nxt, 0, LoopDetector()
            elif turn_bad and bot.escalation and malformed_streak >= bot.escalation.after_malformed:
                esc = ladder.next_escalation()
                nxt = (self._switch(ctx, run, ladder, guard, esc, f"{malformed_streak} malformed tool calls in a row",
                                    "escalation", messages, specs, est_prompt) if esc else None)
                if nxt is not None:
                    session, malformed_streak = nxt, 0
            if malformed_streak >= MAX_MALFORMED_STREAK:
                raise RunAborted("malformed", f"{session.rung.spec} produced {malformed_streak} invalid tool calls in "
                                              "a row; configure an escalation model or choose a more reliable one "
                                              "(see `hutch models bench`)")


def _exit_reason(exc: ProviderError) -> str:
    if getattr(exc, "cost_cap", False):
        return "cost_cap"
    return {"context": "context", "refused": "refused"}.get(exc.kind, "error")


def _keep_resident(ctx: ToolContext, bot) -> bool:
    from ..presets import load_presets
    p = load_presets(ctx.config.state_dir / "presets.json").get(bot.preset or "")
    return bool(p and p.keep_resident)
