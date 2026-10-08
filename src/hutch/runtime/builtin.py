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
import copy
import json
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Callable, Optional

from ..approvals import DeniedError
from ..admission import AdmissionCancelled, AdmissionError, inference_slot
from ..context import check_prompt, plan_context, prompt_tokens as estimate_prompt_tokens, run_selfcheck
from ..hardware import Hardware, probe
from ..models import Event, EventType, Run, RunStatus
from ..providers import ChatRequest, Provider, ProviderError
from ..providers.base import ModelMeta
from ..providers.pricing import PriceBook
from ..store import UsageBudgetRefusal
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

REHEARSAL_NOTE = ("- This is a REHEARSAL (dry run). Reads run for real. Any tool that would change something does NOT run: it "
                  "replies '[rehearsal] would ...' with the policy's verdict. Treat that as success, carry on, and describe "
                  "what you would do and what would need approval.\n")

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
    stream: bool = True


class BuiltinRuntime:
    kind = "builtin"

    def __init__(self, *, hardware: Optional[Hardware] = None, prices: Optional[PriceBook] = None,
                 provider_factory: Optional[Callable[[str, Optional[str]], Provider]] = None,
                 sleep: Callable[[float], None] = time.sleep):
        self._hw = hardware
        self._prices = prices
        self._factory = provider_factory or get_provider
        self._production_factory = provider_factory is None
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
        # Injected snapshots are fixtures; production admission observes current
        # headroom each time, including after a long tool or human wait.
        return self._hw if self._hw is not None else probe(with_runtimes=False)

    def _admission_memory(self, provider, model):
        hw = copy.deepcopy(self._hardware())
        if hw.ram_total_gb <= 0 or hw.ram_available_gb <= 0:
            raise ProviderError("oom", "available RAM could not be measured or is exhausted; no model request was sent")
        cards = [g for g in hw.gpus if not g.integrated and g.vendor in ("nvidia", "amd") and g.vram_gb]
        if hw.accelerator == "gpu" and not any(g.free_gb is not None for g in cards):
            raise ProviderError("oom", "free GPU memory could not be measured; repair the hardware probe before inference")
        # A loaded model's allocation is already deducted from physical free
        # memory. Credit only this model's reported allocation, capped by totals;
        # multi-GPU placement is unknown, so no per-card credit is invented.
        loaded = next((m for m in provider.ps() if m.get("name") == model or m.get("model") == model), None)
        if loaded:
            size, vram = loaded.get("size", 0), loaded.get("size_vram", 0)
            if isinstance(size, (int, float)) and isinstance(vram, (int, float)) and 0 <= vram <= size:
                hw.ram_available_gb = min(hw.ram_total_gb, hw.ram_available_gb + (size - vram) / 1024 ** 3)
                if len(cards) == 1 and cards[0].free_gb is not None:
                    cards[0].free_gb = min(cards[0].vram_gb, cards[0].free_gb + vram / 1024 ** 3)
        return hw, loaded is not None

    @contextmanager
    def _inference(self, ctx: ToolContext, run: Run, rung: Rung, stop=None):
        if not rung.local or rung.provider == "mock":
            yield 0.0
            return
        previous, old_reason = run.status, run.reason
        waited = False
        started = time.perf_counter()

        def cancelled():
            return ctx.closed or ctx.gate.cancelled() or bool(stop and stop())

        def waiting(position):
            nonlocal waited
            reason = f"waiting for local inference: queue position {position} of at most 8; one Hutch call at a time"
            if not ctx.store.set_status(run, RunStatus.waiting_resources,
                                        event={"model": rung.spec, "reason": reason, "queue_position": position},
                                        fields={"reason": reason}):
                raise AdmissionCancelled("the run cannot wait for inference")
            run.reason, waited = reason, True

        try:
            with inference_slot(ctx.config.state_dir, run.id, rung.spec, cancelled, waiting):
                queue_ms = (time.perf_counter() - started) * 1000 if waited else 0.0
                if waited:
                    if not ctx.store.set_status(run, previous, event={"model": rung.spec}, fields={"reason": old_reason}):
                        raise AdmissionCancelled("the run stopped before inference started")
                    run.reason = old_reason
                    run.queue_ms += queue_ms
                    ctx.store.update_run(run)
                    self._log(ctx, run, "resource_wait", f"local inference admitted after {queue_ms / 1000:.2f}s in the queue",
                              model=rung.spec, queue_ms=queue_ms, waiting_limit=8)
                yield queue_ms
        except AdmissionCancelled as exc:
            raise RunAborted("stopped", str(exc)) from exc
        except AdmissionError as exc:
            raise RunAborted("resources", str(exc)) from exc

    def _connections(self, ctx: ToolContext) -> ConnectionBook:
        return ConnectionBook(ctx.config.state_dir)

    def _prices_for(self, ctx: ToolContext) -> PriceBook:
        if self._prices is None:
            self._prices = PriceBook(ctx.config.state_dir / "prices.json")
        self._prices.flat_providers = self._connections(ctx).flat_providers()
        return self._prices

    def _provider_for(self, ctx: ToolContext, ladder: Ladder, rung: Rung, *, expected_route: tuple | None = None,
                      book: ConnectionBook | None = None) -> Provider:
        """A configured Connection wins over a built-in provider name; its terms must be acknowledged first."""
        book = book if book is not None else self._connections(ctx)
        if expected_route is not None and self._route_identity(ctx, ladder, rung, book=book) != expected_route:
            raise ProviderError("bad_request", "provider connection changed after review; no call was sent")
        conn = book.get(rung.provider)
        if conn is None:
            provider = self._factory(rung.provider, ladder.base_url_for(rung))
            if (self._production_factory and expected_route is not None
                    and getattr(provider, "base_url", "").rstrip("/") != expected_route[4].rstrip("/")):
                raise ProviderError("bad_request", "provider endpoint changed after review; no call was sent")
            return provider
        status = book.ack_status(ctx.store, rung.provider)
        if status in ("required", "stale"):
            raise ProviderError(
                "auth", f"the terms of '{conn.title}' have not been acknowledged{' (they changed)' if status == 'stale' else ''}: "
                        f"read them on the Connections page and acknowledge, or run `hutch connections ack {conn.name}`",
                provider=conn.name)
        credential = book.key(conn.name) or ""
        fingerprint = hashlib.sha256(json.dumps(asdict(conn), sort_keys=True).encode() + b"\0" + credential.encode()).hexdigest()
        key = (str(ctx.config.state_dir.resolve()), rung.provider, rung.model, fingerprint)
        cached = _CONN_PROVIDERS.get(key)
        if cached is None:
            cached = _CONN_PROVIDERS[key] = provider_for_connection(book, conn.name, rung.model, resolved_key=credential)
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
        run.model_used = model
        # one transaction: the state change, the fence check and the status event (a stop in flight makes this a no-op)
        ctx.store.set_status(run, status, event={"model": model}, fields={"model_used": model})

    def _interruptible_sleep(self, seconds: float, stop: Callable[[], bool]) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end and not stop():
            self._sleep(min(0.25, max(0.0, end - time.monotonic())))

    # ----------------------------------------------------------- bring online

    def _bring_online(self, ctx: ToolContext, run: Run, ladder: Ladder, rung: Rung, messages: list[dict],
                      specs: list[dict]) -> Session:
        with self._inference(ctx, run, rung):
            return self._prepare_session(ctx, run, ladder, rung, messages, specs)

    def _prepare_session(self, ctx: ToolContext, run: Run, ladder: Ladder, rung: Rung, messages: list[dict],
                         specs: list[dict]) -> Session:
        """Make a rung ready: window, pre-run check, cold load, self-check. Raises ProviderError on failure."""
        bot = ctx.bot
        route = None if rung.local else self._route_identity(ctx, ladder, rung)
        if route is not None and route not in ladder.authorized_routes:
            raise ProviderError("bad_request", "provider connection changed before startup; no call was sent")
        provider = self._provider_for(ctx, ladder, rung, expected_route=route)
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
            hardware, _ = self._admission_memory(provider, rung.model)
            plan = plan_context(meta, hardware, want, floor, local=True)
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

    def _route_identity(self, ctx: ToolContext, ladder: Ladder, rung: Rung, *, book: ConnectionBook | None = None) -> tuple:
        """Billing and destination authority, separate from the selected model and secret."""
        conn = (book if book is not None else self._connections(ctx)).get(rung.provider)
        if conn:
            protocol, endpoint = conn.endpoint_for(rung.model)
            revision = hashlib.sha256(json.dumps(asdict(conn), sort_keys=True).encode()).hexdigest()
            return (conn.name, conn.account_id, conn.billing, protocol, endpoint, revision)
        from ..providers.openai_compat import PRESET_URLS
        import os
        endpoint = ladder.base_url_for(rung) or PRESET_URLS.get(rung.provider, "")
        if rung.provider == "anthropic":
            endpoint = endpoint or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
        elif rung.provider == "openai-compatible":
            endpoint = endpoint or os.environ.get("HUTCH_BASE_URL", "")
        return (rung.provider, rung.provider, "per_token", rung.provider, endpoint, "builtin")

    def _ask_first_hosted(self, ctx: ToolContext, ladder: Ladder, rung: Rung, why: str, est_prompt: int) -> tuple | None:
        """Every new hosted billing/destination authority requires per-run outward approval."""
        if rung.local:
            return
        route = self._route_identity(ctx, ladder, rung)
        if route in ladder.authorized_routes:
            return route
        worst = self._prices_for(ctx).cost(rung.provider, rung.model, est_prompt, self._turn_cap(ctx.bot, rung))
        decision = Decision(Verdict.ask, f"call hosted model {rung.spec}", "",
                            rule="ask:hosted-call", risk="medium")
        ctx.gate.decide(
            "escalation", f"send this run to the hosted model {rung.spec} ({why})",
            {"model": rung.spec, "reason": why, "worst_case_next_call_usd": worst,
             "connection": route[0], "account": route[1], "billing": route[2], "protocol": route[3],
             "destination": route[4], "revision": route[5], "scope": "provider calls in this run on this exact route",
             "what_is_sent": "the conversation so far, including tool results, goes to the model provider"},
            decision, outward=True, ask_in_auto=True)
        if self._route_identity(ctx, ladder, rung) != route:
            raise DeniedError("the provider connection changed during review; no call was sent")
        ladder.authorized_routes.add(route)
        return route

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
        if not rung.local:
            ladder.authorized_routes.add(self._route_identity(ctx, ladder, rung))  # explicit bot/message selection
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
        cost_note = (f", estimated up to ${ceiling:.2f}" if ceiling else ", no per-token cost" if session.rung.local
                     else ", price unknown")
        self._log(ctx, run, "plan", f"{session.rung.spec}: ~{est_prompt:,} prompt tokens, up to "
                                    f"{ctx.bot.limits.max_steps} steps{cost_note}",
                  model=session.rung.spec, window=session.num_ctx, worst_case_usd=ceiling, prompt_tokens=est_prompt)

    # -------------------------------------------------------------------- loop

    def _refresh_local_admission(self, ctx, run, session):
        if session.rung.provider != "ollama" or session.meta is None or not session.num_ctx:
            return  # other local protocols have slot limits, not validated memory admission
        provider, model = session.provider, session.rung.model
        current = provider.show(model)
        if current is None:
            raise ProviderError("model_missing", f"model '{model}' is no longer installed", provider="ollama")
        if session.meta.digest and current.digest != session.meta.digest:
            raise ProviderError("bad_request", "the local model build changed during this run; start a new turn", provider="ollama")
        hardware, loaded = self._admission_memory(provider, model)
        plan = plan_context(current, hardware, session.num_ctx, session.num_ctx, local=True)
        if plan.blocked:
            raise ProviderError("oom", f"insufficient current memory headroom for {session.rung.spec}: {plan.note}", provider="ollama")
        if not loaded:
            self._set_status(ctx, run, RunStatus.loading_model, session.rung.spec)
            try:
                elapsed = provider.preload(model, "10m")
            finally:
                self._set_status(ctx, run, RunStatus.running, session.rung.spec)
            self._log(ctx, run, "load", f"reloaded {model} after another model used inference", load_ms=elapsed)

    def _attempt(self, ctx, run, session, guard, req, est_prompt, stop, ladder, expected_route):
        # Release admission before handling failures, switching routes, tools or
        # approvals. A waiter has not sent a request and must not reserve usage.
        with self._inference(ctx, run, session.rung, stop) as queue_ms:
            book = self._connections(ctx)
            session.provider = self._provider_for(ctx, ladder, session.rung, expected_route=expected_route, book=book)
            guard.connections = book  # the reservation follows this reviewed account's current policy
            self._refresh_local_admission(ctx, run, session)
            try:
                reservation = guard.reserve(session.rung, est_prompt, self._turn_cap(ctx.bot, session.rung))
            except UsageBudgetRefusal as exc:
                reason = str(exc)
                code = "token_cap" if "token" in reason or "allowance" in reason else "cost_cap"
                raise RunAborted(code, reason) from exc
            if stop() or ctx.gate.cancelled():
                ctx.store.release_usage_reservation(reservation, "run stopped before provider call started", expected_fence=run.fence)
                raise RunAborted("stopped", "user requested stop")
            t_call = time.perf_counter()
            try:
                result = session.provider.chat(req)
            except ProviderError as exc:
                ctx.store.mark_usage_uncertain(reservation, f"provider outcome is uncertain ({exc.kind})", expected_fence=run.fence)
                raise
            except Exception as exc:
                ctx.store.mark_usage_uncertain(reservation, f"provider call ended with {type(exc).__name__}", expected_fence=run.fence)
                raise
            return result, reservation, t_call, queue_ms

    def execute(self, run: Run, ctx: ToolContext, tools: dict[str, Tool], stop: Callable[[], bool]) -> str:
        bot = ctx.bot
        ladder = Ladder(bot)
        prices = self._prices_for(ctx)
        guard = SpendGuard(ctx.store, bot, run, prices, self._connections(ctx))
        system = self._system_prompt(ctx)
        specs = [tools[n].spec() for n in sorted(tools)]             # PF-1 / PF-3: frozen, deterministic, allowed only
        prefix_hash = hashlib.sha256((system + json.dumps(specs, sort_keys=True)).encode()).hexdigest()[:12]
        messages: list[dict[str, Any]] = [{"role": "system", "content": system},
                                          *run.conversation_context,
                                          {"role": "user", "content": run.prompt}]
        mt, tt = estimate_prompt_tokens(messages, specs)
        est_prompt = mt + tt
        run.model_used = ladder.primary.spec

        session = self._start(ctx, run, ladder, guard, messages, specs, stop, est_prompt)
        loop = LoopDetector()
        malformed_streak = loop_strikes = 0
        rate_limited_once = False
        stream_retried = False
        warned_quota: set[str] = set()

        while True:
            if stop():
                raise RunAborted("stopped", "user requested stop")
            if run.steps >= bot.limits.max_steps:
                raise RunAborted("steps_exceeded", f"hit max_steps={bot.limits.max_steps}")
            if ctx.store.tokens_today(bot.id) > bot.limits.daily_token_cap:
                raise RunAborted("token_cap", f"daily cap {bot.limits.daily_token_cap} exceeded")
            guard.connections = self._connections(ctx)
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
            try:
                route = self._ask_first_hosted(ctx, ladder, session.rung, "the connection authority changed", est_prompt)
                session.provider = self._provider_for(ctx, ladder, session.rung, expected_route=route)
            except DeniedError as exc:
                raise RunAborted("error", f"provider route was not approved: {exc}") from exc
            except ProviderError as exc:
                raise RunAborted(_exit_reason(exc), f"provider connection is no longer usable: {exc}") from exc
            req = ChatRequest(
                model=session.rung.model, messages=messages, tools=specs, num_ctx=session.num_ctx,
                max_tokens=self._turn_cap(bot, session.rung), think=bot.think if bot.think is not None else False,
                stream=session.stream, allow_stream_retry=False,
                register_cancel=self._register_cancel(ctx), is_cancelled=stop, session_id=run.id,
                keep_alive="30m" if _keep_resident(ctx, bot) else "10m")
            account_id, _, _ = guard.account_policy(session.rung)
            try:
                result, reservation_id, t_call, timer.queue_ms = self._attempt(
                    ctx, run, session, guard, req, est_prompt, stop, ladder, route)
                record_outcome(ctx.store, session.rung.provider, True)
            except ProviderError as exc:
                if stop():
                    raise RunAborted("stopped", "user requested stop") from exc
                record_outcome(ctx.store, session.rung.provider, False, f"{exc.kind}: {exc}")
                if exc.streaming_related and session.stream and not stream_retried:
                    stream_retried = True
                    session.stream = False
                    self._log(ctx, run, "stream_retry", f"streaming failed ({exc}); next attempt without streaming. "
                              "Previous usage remains reserved pending reconciliation.")
                    continue  # the next attempt must acquire its own shared-account reservation
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
            except RunAborted:
                raise
            except Exception as exc:
                raise
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
                        cost_usd=cost or 0.0, account_id=account_id, reservation_id=reservation_id,
                        prefix=prefix_hash, window=session.num_ctx or 0,
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

            # The estimate limit stops FURTHER model calls; it never discards a final answer already paid for.
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
