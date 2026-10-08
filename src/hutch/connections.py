"""Connections: named endpoints and subscription plans, each with its own key (CN-1..CN-8).

Why this exists. Pointing Hutch at "any OpenAI-compatible URL" was possible by hand, but with ONE global
``OPENAI_API_KEY`` for every such URL, no notion of a flat-rate plan, no per-model protocol, no required headers and
no warning about a vendor's terms, it was not usable for the subscription plans people actually own now:

* OpenCode Go - a flat subscription, one key, many models; clients must send their own User-Agent and a stable
  session id, and "traffic is monitored for abuse".
* Xiaomi MiMo Token Plan - ``tp-`` keys, OpenAI *and* Anthropic compatible endpoints per region, billed in Credits.

A Connection fixes that:
* its own key, from an environment variable or a 0600 file under the state dir - never written to the database,
  the transcript, the API or a page;
* a protocol per model (some plans serve different models over different wire formats);
* the headers a plan requires (User-Agent, a per-run session id);
* a billing mode - ``per_token`` (priced from prices.json), ``subscription`` (flat; cost 0 but *usage is tracked*)
  or ``free`` - and a declared allowance that Hutch enforces BEFORE the vendor does, because "42% of my weekly
  allowance gone on day one" is the loudest complaint about the products Hutch is measured against;
* a terms notice that must be acknowledged once (and again if the notice changes) before the first run.

What this deliberately is NOT: logging in with a consumer plan's OAuth session (Claude Pro/Max, ChatGPT). Those
vendors' terms restrict consumer-plan tokens to their own apps and prohibit automated access except via API key
(LM-15), so Hutch never reads, stores or proxies such tokens. Subscription plans that issue an API key are fine.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Optional

WINDOWS = {"5h": 5 * 3600, "day": 24 * 3600, "week": 7 * 24 * 3600, "month": 30 * 24 * 3600}
PROTOCOLS = ("openai-chat", "anthropic")
UNSUPPORTED_PROTOCOLS = ("openai-responses",)
BILLING = ("per_token", "subscription", "free")
RESERVED = {"ollama", "openai", "anthropic", "lmstudio", "llamacpp", "llama.cpp", "vllm", "mock",
            "openai-compatible"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


@dataclass
class Terms:
    url: str = ""
    notice: str = ""
    requires_ack: bool = False

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.notice.encode()).hexdigest()[:12]


@dataclass
class Quota:
    window: str = "month"        # 5h | day | week | month  (rolling windows: a conservative approximation)
    tokens: int = 0              # 0 = no allowance declared
    warn_at: float = 0.8

    @property
    def seconds(self) -> int:
        return WINDOWS.get(self.window, WINDOWS["month"])


@dataclass
class Connection:
    name: str
    template: str
    title: str
    protocol: str
    base_url: str
    api_key_env: str
    billing: str
    account_id: str
    account_daily_cost_cap_usd: float = 0.0
    anthropic_base_url: str = ""
    session_header: str = ""
    user_agent: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    model_protocols: dict[str, str] = field(default_factory=dict)
    quota: Quota = field(default_factory=Quota)
    terms: Terms = field(default_factory=Terms)
    get_key_url: str = ""
    source: str = ""
    models_endpoint: bool = True
    quota_hint: str = ""
    model_protocol_hint: str = ""

    def endpoint_for(self, model: str) -> tuple[str, str]:
        """(protocol, base url) for one model: plans may serve different models over different protocols."""
        proto = self.model_protocols.get(model, self.protocol)
        if proto == "anthropic" and self.protocol != "anthropic":
            return proto, self.anthropic_base_url or self.base_url
        return proto, self.base_url

    @property
    def flat(self) -> bool:
        return self.billing in ("subscription", "free")


def _version() -> str:
    from . import __version__
    return __version__


def load_templates() -> dict[str, dict[str, Any]]:
    path = Path(str(resources.files("hutch") / "data" / "connections.json"))
    return json.loads(path.read_text())["templates"]


class ConnectionBook:
    """Templates + the user's configured connections (``<state dir>/connections.json``) + their keys."""

    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / "connections.json"
        self.keys_dir = self.state_dir / "keys"
        self._templates = load_templates()
        self._conns: dict[str, Connection] = {}
        self.errors: list[str] = []
        self._load()

    # ------------------------------------------------------------- loading

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text()).get("connections", {}) if self.path.exists() else {}
        except (OSError, json.JSONDecodeError) as exc:
            self.errors.append(f"{self.path}: {exc}")
            return {}

    def _load(self) -> None:
        for name, row in self._read().items():
            try:
                self._conns[name] = self._build(name, row)
            except (KeyError, ValueError, TypeError) as exc:
                self.errors.append(f"connection '{name}': {exc}")

    def _build(self, name: str, row: dict[str, Any]) -> Connection:
        tpl = dict(self._templates.get(row.get("template", ""), {}))
        merged = {**tpl, **{k: v for k, v in row.items() if v is not None}}
        terms = {**tpl.get("terms", {}), **row.get("terms", {})}
        q = row.get("quota") or {}
        proto = merged.get("protocol", "openai-chat")
        if proto in UNSUPPORTED_PROTOCOLS:
            raise ValueError(f"protocol '{proto}' is not supported yet (use openai-chat or anthropic)")
        if proto not in PROTOCOLS:
            raise ValueError(f"unknown protocol '{proto}'")
        billing = merged.get("billing", "per_token")
        if billing not in BILLING:
            raise ValueError(f"unknown billing mode '{billing}'")
        account_id = str(merged.get("account_id") or name).strip().lower()
        if not SLUG.fullmatch(account_id):
            raise ValueError("account_id must be a lowercase slug: a-z, 0-9 and hyphens, 2-41 characters")
        account_cap = float(merged.get("account_daily_cost_cap_usd", 0) or 0)
        if not math.isfinite(account_cap) or account_cap < 0:
            raise ValueError("account_daily_cost_cap_usd must be a finite non-negative number")
        for m, p in (merged.get("model_protocols") or {}).items():
            if p not in PROTOCOLS:
                raise ValueError(f"model '{m}': protocol '{p}' is not supported")
        quota_window = q.get("window", "month")
        quota_tokens = int(q.get("tokens", 0) or 0)
        quota_warn_at = float(q.get("warn_at", 0.8))
        if quota_window not in WINDOWS:
            raise ValueError(f"quota window must be one of {', '.join(WINDOWS)}")
        if quota_tokens < 0:
            raise ValueError("quota tokens must be non-negative")
        if not math.isfinite(quota_warn_at) or not 0 <= quota_warn_at <= 1:
            raise ValueError("quota warn_at must be between 0 and 1")
        return Connection(
            name=name, template=row.get("template", ""), title=merged.get("title", name), protocol=proto,
            base_url=merged["base_url"].rstrip("/"), api_key_env=merged.get("api_key_env", ""), billing=billing,
            account_id=account_id, account_daily_cost_cap_usd=account_cap,
            anthropic_base_url=(merged.get("anthropic_base_url") or "").rstrip("/"),
            session_header=merged.get("session_header", ""),
            user_agent=(merged.get("user_agent") or f"hutch/{_version()}").replace("{version}", _version()),
            headers=dict(merged.get("headers") or {}), model_protocols=dict(merged.get("model_protocols") or {}),
            quota=Quota(window=quota_window, tokens=quota_tokens, warn_at=quota_warn_at),
            terms=Terms(url=terms.get("url", ""), notice=terms.get("notice", ""),
                        requires_ack=bool(terms.get("requires_ack"))),
            get_key_url=merged.get("get_key_url", ""), source=merged.get("source", ""),
            models_endpoint=bool(merged.get("models_endpoint", True)), quota_hint=merged.get("quota_hint", ""),
            model_protocol_hint=merged.get("model_protocol_hint", ""))

    def _write(self, rows: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"connections": rows}, indent=2) + "\n")
        os.replace(tmp, self.path)
        self._conns.clear()
        self._load()

    # -------------------------------------------------------------- queries

    def templates(self) -> dict[str, dict[str, Any]]:
        return self._templates

    def configured(self) -> dict[str, Connection]:
        return dict(self._conns)

    def get(self, name: str) -> Optional[Connection]:
        return self._conns.get(name)

    def names(self) -> set[str]:
        return set(self._conns)

    def flat_providers(self) -> set[str]:
        return {n for n, c in self._conns.items() if c.flat}

    def account_policy(self, account_id: str) -> tuple[float, list[tuple[int, float]]]:
        """Return the strictest declared cost cap and every token window shared by this billing account."""
        members = [conn for conn in self._conns.values() if conn.account_id == account_id]
        cost_caps = [conn.account_daily_cost_cap_usd for conn in members if conn.account_daily_cost_cap_usd > 0]
        quotas = sorted({(conn.quota.tokens, float(conn.quota.seconds)) for conn in members if conn.quota.tokens > 0})
        return (min(cost_caps) if cost_caps else 0.0), quotas

    # ----------------------------------------------------------------- keys

    def key_file(self, name: str) -> Path:
        return self.keys_dir / f"{name}.key"

    def key(self, name: str) -> Optional[str]:
        """The API key: the environment variable first, then the 0600 file. Never logged or returned by the API."""
        conn = self._conns.get(name)
        if conn is None:
            return None
        if conn.api_key_env and os.environ.get(conn.api_key_env):
            return os.environ[conn.api_key_env].strip()
        f = self.key_file(name)
        try:
            return f.read_text().strip() or None
        except OSError:
            return None

    def key_source(self, name: str) -> str:
        conn = self._conns.get(name)
        if conn and conn.api_key_env and os.environ.get(conn.api_key_env):
            return f"environment variable {conn.api_key_env}"
        if self.key_file(name).exists():
            return "key file in the state directory"
        return "missing"

    def set_key(self, name: str, value: str) -> None:
        if name not in self._conns:
            raise KeyError(name)
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.keys_dir, 0o700)
        f = self.key_file(name)
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # created 0600, never world-readable
        with os.fdopen(fd, "w") as fh:
            fh.write(value.strip() + "\n")
        os.chmod(f, 0o600)

    def clear_key(self, name: str) -> None:
        try:
            self.key_file(name).unlink()
        except OSError:
            pass

    # ------------------------------------------------------------ mutation

    def add(self, template: str, name: Optional[str] = None, **overrides: Any) -> Connection:
        if template not in self._templates:
            raise ValueError(f"unknown template '{template}' (see `hutch connections templates`)")
        name = name or template
        if not SLUG.match(name):
            raise ValueError("name must be a lowercase slug: a-z, 0-9 and hyphens, 2-41 characters")
        if name in RESERVED:
            raise ValueError(f"'{name}' is a built-in provider name; pick another")
        rows = self._read()
        if name in rows:
            raise ValueError(f"connection '{name}' already exists")
        row = {"template": template, **{k: v for k, v in overrides.items() if v not in (None, "")}}
        self._build(name, row)                                          # validate before writing
        rows[name] = row
        self._write(rows)
        return self._conns[name]

    def update(self, name: str, **fields: Any) -> Connection:
        rows = self._read()
        if name not in rows:
            raise KeyError(name)
        for k, v in fields.items():
            if v is None:
                rows[name].pop(k, None)
            else:
                rows[name][k] = v
        self._build(name, rows[name])
        self._write(rows)
        return self._conns[name]

    def set_model_protocol(self, name: str, model: str, protocol: str) -> Connection:
        rows = self._read()
        if name not in rows:
            raise KeyError(name)
        if protocol in UNSUPPORTED_PROTOCOLS:
            raise ValueError(f"protocol '{protocol}' is not supported yet (use openai-chat or anthropic)")
        mp = dict(rows[name].get("model_protocols") or {})
        mp[model] = protocol
        return self.update(name, model_protocols=mp)

    def set_quota(self, name: str, window: str, tokens: int, warn_at: float = 0.8) -> Connection:
        if window not in WINDOWS:
            raise ValueError(f"window must be one of {', '.join(WINDOWS)}")
        return self.update(name, quota={"window": window, "tokens": int(tokens), "warn_at": warn_at})

    def remove(self, name: str) -> bool:
        rows = self._read()
        if name not in rows:
            return False
        rows.pop(name)
        self._write(rows)
        self.clear_key(name)
        return True

    # -------------------------------------------------- terms acknowledgement

    def ack_status(self, store: Any, name: str) -> str:
        """not_needed | ok | required | stale (the notice changed since it was acknowledged)."""
        conn = self._conns.get(name)
        if conn is None or not conn.terms.requires_ack:
            return "not_needed"
        raw = store.kv_get(f"connection_ack:{name}")
        if not raw:
            return "required"
        try:
            return "ok" if json.loads(raw).get("digest") == conn.terms.digest else "stale"
        except (ValueError, AttributeError):
            return "required"

    def acknowledge(self, store: Any, name: str) -> None:
        from .models import iso, utcnow
        conn = self._conns[name]
        store.kv_set(f"connection_ack:{name}", json.dumps({"digest": conn.terms.digest, "at": iso(utcnow())}))
