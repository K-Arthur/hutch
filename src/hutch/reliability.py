"""Reliability harness (LM-11): measure what a model actually does with tools, per model / quant / runtime / template.

Why: the same model name behaves differently by quantisation, runtime and chat template, and "supports tools" on a
model card is not the same as "forms a valid call, with the right types, picks the right tool among several, stops
when it should, and uses what the tool returned" (the documented failure of small local models in agent loops).
Marketing numbers do not help a person choosing between three installed models; measurements on their own machine do.

Each probe is a small deterministic task run ``trials`` times at a little temperature (so a flaky model shows up as
flaky). A probe records two numbers, because Hutch repairs safe slips before running a tool (LM-13):

* ``raw``      the model did it right unaided;
* ``repaired`` it is right once Hutch's silent coercion ("3" -> 3, "true" -> true) is applied.

The verdict is computed from ``repaired`` (what a bot will experience) and shows ``raw`` so a model that only works
thanks to repair is visible as such. Nothing here is a leaderboard score: it is a profile of one model on one machine.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

from .context import run_selfcheck
from .models import iso, utcnow
from .providers.base import ChatRequest, ChatResult, Provider, ProviderError
from .runtime.toolrepair import coerce_args, validate_args

DEFAULT_TRIALS = 3
TEMPERATURE = 0.3


def _tool(name: str, description: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": props, "required": required}}}


READ = _tool("read_file", "Read a text file from the workspace.", {"path": {"type": "string", "description": "file path"}}, ["path"])
WRITE = _tool("write_file", "Write text to a file in the workspace.",
              {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"])
LIST = _tool("list_files", "List the files in a folder of the workspace.", {"path": {"type": "string"}}, ["path"])
SHELL = _tool("shell", "Run a shell command.", {"command": {"type": "string"}}, ["command"])
FETCH = _tool("web_fetch", "Fetch a web page and return its text.", {"url": {"type": "string"}}, ["url"])
ADD = _tool("add_item", "Add an item to the shopping list.",
            {"name": {"type": "string"}, "quantity": {"type": "integer"}, "urgent": {"type": "boolean"}},
            ["name", "quantity", "urgent"])


@dataclass
class Judgement:
    raw: bool
    repaired: bool
    why: str = ""


@dataclass
class ProbeResult:
    id: str
    title: str
    trials: int
    raw: int = 0
    repaired: int = 0
    errors: int = 0                         # the model call itself failed (runtime problem, not model quality)
    detail: str = ""                        # the most common way it went wrong
    median_ms: float = 0.0

    @property
    def rate(self) -> float:
        return self.repaired / self.trials if self.trials else 0.0


@dataclass
class Profile:
    model: str                              # "ollama/qwen3:4b"
    quant: str
    runtime: str
    template_hash: str
    digest: str
    num_ctx: int
    hardware: str
    measured_at: str
    probes: list[ProbeResult] = field(default_factory=list)
    tokens_per_sec: Optional[float] = None
    load_ms: Optional[float] = None
    verdict: str = ""                       # reliable | usable_with_repair | unreliable | inconclusive
    summary: str = ""

    @property
    def key(self) -> str:
        return profile_key(self.model, self.quant, self.runtime, self.template_hash, self.digest, self.num_ctx)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(raw: str) -> "Profile":
        d = json.loads(raw)
        d["probes"] = [ProbeResult(**p) for p in d.get("probes", [])]
        return Profile(**d)

    def probe(self, pid: str) -> Optional[ProbeResult]:
        return next((p for p in self.probes if p.id == pid), None)


def profile_key(model: str, quant: str, runtime: str, template_hash: str, digest: str, num_ctx: int) -> str:
    return hashlib.sha256("|".join([model, quant, runtime, template_hash, digest, str(num_ctx)]).encode()).hexdigest()[:20]


# ------------------------------------------------------------------ judging

def _single_call(res: ChatResult, name: str, tools: list[dict]) -> tuple[Optional[dict], Optional[dict], str]:
    """The one call the model made as (raw args, repaired args, why-not)."""
    if not res.tool_calls:
        return None, None, "answered in prose instead of calling the tool" if res.content.strip() else "returned nothing"
    if len(res.tool_calls) != 1:
        return None, None, f"made {len(res.tool_calls)} calls where one was asked for"
    tc = res.tool_calls[0]
    if tc.name != name:
        return None, None, f"called '{tc.name}' instead of '{name}'"
    if tc.parse_error:
        return None, None, f"arguments were not valid JSON ({tc.parse_error})"
    schema = next(t["function"]["parameters"] for t in tools if t["function"]["name"] == name)
    return tc.arguments, coerce_args(schema, dict(tc.arguments))[0], ""


def _judge_call(name: str, tools: list[dict], semantic: Callable[[dict], str]) -> Callable[[ChatResult], Judgement]:
    schema = next(t["function"]["parameters"] for t in tools if t["function"]["name"] == name)

    def judge(res: ChatResult) -> Judgement:
        raw, fixed, why = _single_call(res, name, tools)
        if raw is None:
            return Judgement(False, False, why)
        bad_raw, bad_fixed = validate_args(schema, raw), validate_args(schema, fixed)
        sem_fixed = semantic(fixed) if not bad_fixed else ""
        if bad_fixed:
            return Judgement(False, False, "arguments do not match the tool's schema: " + "; ".join(bad_fixed))
        if sem_fixed:
            return Judgement(False, False, sem_fixed)
        return Judgement(not bad_raw and not semantic(raw), True, "" if not bad_raw else "needed type repair")
    return judge


def _has(args: dict, key: str, needle: str) -> bool:
    return needle.lower() in str(args.get(key, "")).lower()


def _sem_read(a: dict) -> str:
    return "" if _has(a, "path", "notes.txt") else f"asked for the wrong file ({a.get('path')!r})"


def _sem_add(a: dict) -> str:
    if not _has(a, "name", "banana"):
        return f"wrong item name ({a.get('name')!r})"
    if a.get("quantity") != 3:
        return f"wrong quantity ({a.get('quantity')!r})"
    if a.get("urgent") is not True:
        return f"urgent was not set ({a.get('urgent')!r})"
    return ""


def _sem_list(a: dict) -> str:
    return "" if _has(a, "path", "reports") else f"listed the wrong folder ({a.get('path')!r})"


def _judge_restraint(res: ChatResult) -> Judgement:
    if res.tool_calls:
        return Judgement(False, False, f"called '{res.tool_calls[0].name}' for a question that needs no tool")
    ok = "4" in res.content
    return Judgement(ok, ok, "" if ok else "did not answer 4")


def _judge_uses_result(res: ChatResult) -> Judgement:
    if res.tool_calls:
        return Judgement(False, False, "called a tool again instead of using the result it already had")
    ok = "3" in res.content
    return Judgement(ok, ok, "" if ok else "ignored the tool result (did not say 3pm)")


@dataclass
class Probe:
    id: str
    title: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    judge: Callable[[ChatResult], Judgement]


def probes() -> list[Probe]:
    return [
        Probe("call_shape", "Forms a valid tool call",
              [{"role": "user", "content": "Read the file named notes.txt."}], [READ],
              _judge_call("read_file", [READ], _sem_read)),
        Probe("arg_types", "Gets argument types right (int, bool)",
              [{"role": "user", "content": "Add 3 bananas to the list and mark them urgent."}], [ADD],
              _judge_call("add_item", [ADD], _sem_add)),
        Probe("tool_choice", "Picks the right tool among five",
              [{"role": "user", "content": "List the files in the folder reports."}], [READ, WRITE, LIST, SHELL, FETCH],
              _judge_call("list_files", [READ, WRITE, LIST, SHELL, FETCH], _sem_list)),
        Probe("restraint", "Does not call a tool it does not need",
              [{"role": "user", "content": "What is 2 + 2? Answer directly."}], [READ, LIST], _judge_restraint),
        Probe("uses_result", "Uses what a tool returned",
              [{"role": "user", "content": "What time is the meeting? Check notes.txt if you need to."},
               {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {
                   "name": "read_file", "arguments": json.dumps({"path": "notes.txt"})}}]},
               {"role": "tool", "tool_call_id": "call_1", "name": "read_file",
                "content": "Meeting moved to 3pm on Thursday."}], [READ, LIST], _judge_uses_result),
    ]


# ------------------------------------------------------------------ running

def _verdict(probe_results: list[ProbeResult], recall_ok: Optional[bool]) -> tuple[str, str]:
    tool = [p for p in probe_results if p.id != "long_context"]
    done = [p for p in tool if p.errors < p.trials]
    if not done or sum(p.errors for p in tool) >= sum(p.trials for p in tool) * 0.5:
        return "inconclusive", "more than half the calls failed at the runtime level, so quality could not be judged"
    worst = min(done, key=lambda p: p.rate)
    raw_rate = sum(p.raw for p in done) / sum(p.trials for p in done)
    rep_rate = sum(p.repaired for p in done) / sum(p.trials for p in done)
    weak = [p.title.lower() for p in done if p.rate < 0.8]
    if rep_rate >= 0.9 and worst.rate >= 0.67:
        v = "reliable" if raw_rate >= 0.9 else "usable_with_repair"
        s = (f"{rep_rate:.0%} of tool probes passed" + ("" if v == "reliable" else
             f" ({raw_rate:.0%} unaided: it leans on Hutch's argument repair)"))
    else:
        v = "unreliable"
        s = f"{rep_rate:.0%} of tool probes passed; weakest: {worst.title.lower()} ({worst.repaired}/{worst.trials})"
    if weak and v != "unreliable":
        s += f"; shaky at: {', '.join(weak)}"
    if recall_ok is False:
        s += "; could not recall the start of a long prompt at this window"
    return v, s


def profile_model(provider: Provider, model: str, *, runtime: str = "ollama", num_ctx: int = 8192,
                  trials: int = DEFAULT_TRIALS, hardware: str = "", with_recall: bool = True,
                  progress: Optional[Callable[[str], None]] = None) -> Profile:
    """Run every probe ``trials`` times against ``model`` (bare name, as the runtime knows it)."""
    say = progress or (lambda s: None)
    meta = None
    try:
        meta = provider.show(model)
    except Exception:
        pass
    digest = ""
    try:
        digest = next((m.digest for m in provider.list_models() if m.name == model), "")
    except Exception:
        pass
    prof = Profile(model=f"{runtime}/{model}", quant=getattr(meta, "quant", "") or "", runtime=runtime,
                   template_hash=getattr(meta, "template_hash", "") or "", digest=digest, num_ctx=num_ctx,
                   hardware=hardware, measured_at=iso(utcnow()))
    speeds: list[float] = []
    loads: list[float] = []
    for pr in probes():
        res = ProbeResult(pr.id, pr.title, trials)
        times: list[float] = []
        reasons: dict[str, int] = {}
        say(f"{pr.title} ...")
        for _ in range(trials):
            t0 = time.perf_counter()
            try:
                out = provider.chat(ChatRequest(model=model, messages=list(pr.messages), tools=pr.tools, num_ctx=num_ctx,
                                                max_tokens=256, temperature=TEMPERATURE, think=False))
            except ProviderError as exc:
                res.errors += 1
                reasons[f"the call failed ({exc.kind})"] = reasons.get(f"the call failed ({exc.kind})", 0) + 1
                continue
            times.append((time.perf_counter() - t0) * 1000)
            if out.tokens_per_sec:
                speeds.append(out.tokens_per_sec)
            if out.load_ms:
                loads.append(out.load_ms)
            j = pr.judge(out)
            res.raw += j.raw
            res.repaired += j.repaired
            if not j.repaired and j.why:
                reasons[j.why] = reasons.get(j.why, 0) + 1
        res.median_ms = round(statistics.median(times), 1) if times else 0.0
        res.detail = max(reasons, key=reasons.get) if reasons else ""
        prof.probes.append(res)
    recall: Optional[bool] = None
    if with_recall:
        say("recalls a code word from the top of a long prompt ...")
        sc = run_selfcheck(provider, model, num_ctx)
        recall = sc.ok
        prof.probes.append(ProbeResult("long_context", "Recalls the start of a long prompt", 1, int(sc.ok), int(sc.ok),
                                       1 if sc.error_kind else 0, "" if sc.ok else sc.detail, round(sc.seconds * 1000, 1)))
    prof.tokens_per_sec = round(statistics.median(speeds), 1) if speeds else None
    prof.load_ms = round(max(loads), 1) if loads else None
    prof.verdict, prof.summary = _verdict(prof.probes, recall)
    return prof


VERDICT_TEXT = {
    "reliable": "reliable with tools",
    "usable_with_repair": "works, leaning on argument repair",
    "unreliable": "unreliable with tools",
    "inconclusive": "inconclusive",
}
