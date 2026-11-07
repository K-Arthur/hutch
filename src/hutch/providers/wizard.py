"""Per-route setup guides for the provider detail page.

A route is one auth method of a provider. For each, this module derives the ordered steps a person must
take from facts that exist now: the catalogue, the connection templates, the account book, the local-service
probes and the runtime registry. Nothing here contacts a provider, reads a credential value (only whether
one exists) or changes state; the page's forms do that through ConnectionBook.

A route Hutch has not built, or one the provider blocks, gets one honest step that says so. It never gets a
form, so the page cannot invite someone to configure something that will not work.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional

from ..connections import ConnectionBook
from .catalog import STATUS_TEXT, AuthMethod, Provider
from .catalog_view import CODE_LABELS

STATE_TEXT = {"done": "Done", "current": "Next", "todo": "Later", "blocked": "Blocked", "info": "Note"}
_BUILT = ("implemented", "experimental")
_SIGN_IN = ("oauth", "pkce", "device_code")


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    state: str
    body: str = ""
    link: Optional[tuple[str, str]] = None
    form: str = ""                       # connect | key | ack | test, rendered by the template
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def state_text(self) -> str:
        return STATE_TEXT.get(self.state, self.state)


@dataclass(frozen=True)
class RouteGuide:
    method: AuthMethod
    code_label: str
    accounts: tuple[str, ...]
    focus: str
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class Context:
    """Everything a builder may read, assembled once per page view."""

    provider: Provider
    book: ConnectionBook
    store: Any
    templates: dict[str, dict[str, Any]]
    local_services: tuple[dict[str, Any], ...]
    runtimes: tuple[dict[str, Any], ...]
    media_env: str
    focus: str


def _first_open(steps: list[Step]) -> list[Step]:
    """Mark the first step that is not done as the one to do next; later undone steps are 'later'."""
    out, seen = [], False
    for step in steps:
        if step.state in ("current", "todo") and not seen:
            out.append(replace(step, state="current"))
            seen = True
        elif step.state == "current":
            out.append(replace(step, state="todo"))
        else:
            out.append(step)
    return out


def _templates_for(ctx: Context, method: AuthMethod) -> list[tuple[str, dict[str, Any]]]:
    return [(tid, ctx.templates[tid]) for tid in ctx.provider.connection_templates
            if tid in ctx.templates and ctx.templates[tid].get("auth_method", "api_key") == method.type]


def _accounts(ctx: Context, template_ids: list[str]) -> list[str]:
    return sorted(name for name, conn in ctx.book.configured().items() if conn.template in template_ids)


def _focus(ctx: Context, accounts: list[str]) -> str:
    return ctx.focus if ctx.focus in accounts else (accounts[0] if accounts else "")


# ------------------------------------------------------------------------------------ api key / endpoint

def _placeholder_url(url: str) -> bool:
    """A custom template ships a bare scheme ("https://") that only marks where the operator's URL goes."""
    return not url or url.rstrip("/") in ("http:", "https:")


def _add_step(offers: list[tuple[str, dict[str, Any]]], focus: str, method: AuthMethod) -> Step:
    choices = [{"id": tid, "title": tpl.get("title", tid),
                "needs_base_url": _placeholder_url(str(tpl.get("base_url") or "")),
                "asks_base_url": method.type == "custom_endpoint"}
               for tid, tpl in offers]
    body = ("This account exists. Add another one for a different key or region."
            if focus else "Create a named connection. Its name is what a model spec uses, so it always says who pays.")
    return Step("add", "Add the account", "done" if focus else "todo", body, form="connect",
                data={"choices": choices})


def _key_step(ctx: Context, offers: list[tuple[str, dict[str, Any]]], focus: str) -> Step:
    conn = ctx.book.get(focus) if focus else None
    tpl = ctx.templates.get(conn.template, {}) if conn else (offers[0][1] if offers else {})
    guidance = tpl.get("signin_guidance") or "Create an API key in the provider's console."
    url = tpl.get("get_key_url") or ""
    env = (conn.api_key_env if conn else tpl.get("api_key_env")) or ""
    have = bool(focus) and ctx.book.has_key(focus)
    body = guidance + (f" Or set {env} where Hutch starts; that variable then overrides the stored key." if env else "")
    if have:
        body = "A key is present: " + ctx.book.key_source(focus) + ". " + body
    return Step("key", "Store the key", "done" if have else ("todo" if focus else "blocked"), body,
                link=("Open the provider's console", url) if url.startswith("https://") else None,
                form="key" if focus else "", data={"account": focus})


def _ack_step(ctx: Context, focus: str) -> Optional[Step]:
    status = ctx.book.ack_status(ctx.store, focus) if focus else "not_needed"
    if status == "not_needed":
        return None
    conn = ctx.book.get(focus)
    notice = conn.terms.notice if conn else ""
    state = "done" if status == "ok" else "todo"
    return Step("ack", "Read the provider's terms", state, notice, form="ack" if state != "done" else "",
                link=(("Provider terms", conn.terms.url) if conn and conn.terms.url.startswith("https://") else None),
                data={"account": focus, "stale": status == "stale"})


def _test_step(focus: str, ready: bool) -> Step:
    body = ("Asks the provider's model list endpoint whether the key works. It sends no prompt and costs nothing "
            "to run; a list that answers is reachability evidence, not proof that a model will run.")
    return Step("test", "Test the connection", "todo" if ready else "blocked", body,
                form="test" if ready else "", data={"account": focus})


def _key_route(ctx: Context, method: AuthMethod) -> list[Step]:
    offers = _templates_for(ctx, method)
    if not offers:
        return _env_route(ctx, method) if ctx.media_env else _no_template(method)
    ids = [tid for tid, _ in offers]
    accounts = _accounts(ctx, ids)
    focus = _focus(ctx, accounts)
    steps = [_add_step(offers, focus, method), _key_step(ctx, offers, focus)]
    ack = _ack_step(ctx, focus)
    if ack:
        steps.append(ack)
    ready = all(step.state == "done" for step in steps)
    steps.append(_test_step(focus, ready))
    steps.append(Step("model", "Choose a model", "info" if ready else "blocked",
                      "Name the account in the model spec and check the resolved route before the first send.",
                      link=("Check a route", "#route-picker")))
    return _first_open(steps)


def _no_template(method: AuthMethod) -> list[Step]:
    return [Step("template", "No setup form yet", "info",
                 "Hutch has no connection template for this route, so it cannot be set up from here. "
                 + (method.notes or ""))]


def _env_route(ctx: Context, method: AuthMethod) -> list[Step]:
    present = bool(os.environ.get(ctx.media_env))
    body = (f"Hutch reads this vendor's key from the environment variable {ctx.media_env} where it starts, and the "
            "approval names it as ambient. There is no stored-key form for this vendor yet.")
    return [Step("env", f"Set {ctx.media_env}", "done" if present else "current", body + (
        " The variable is set in Hutch's environment." if present else " The variable is not set."))]


# ------------------------------------------------------------------ sign-in, CLI, local service, not built

def _sign_in_route(ctx: Context, method: AuthMethod) -> list[Step]:
    ids = [tid for tid, _ in _templates_for(ctx, method)]
    active = any(ctx.book.has_key(name) for name in _accounts(ctx, ids))
    body = ("Subscription sign-ins are started from Apps & AI, which owns the redirect and the account record. "
            + (method.notes or ""))
    return [Step("sign-in", "Sign in", "done" if active else "current", body.strip(),
                 link=("Open Apps & AI", "/#/connections"))]


def _cli_route(ctx: Context, method: AuthMethod) -> list[Step]:
    runtime = next((item for item in ctx.runtimes if item.get("id") == ctx.provider.id), None)
    cli = (runtime or {}).get("cli") or {}
    installed = bool(cli.get("installed"))
    version = f" ({cli['version']})" if cli.get("version") else ""
    first = Step("cli", "Install the official command-line tool", "done" if installed else "current",
                 ("Detected" + version + ". " if installed else "Not found on this machine. ") + (method.notes or ""))
    second = Step("cli-sign-in", "Sign in inside that tool", "todo",
                  "Hutch never sees or stores this sign-in; the tool owns it and its own tools and permissions.")
    return _first_open([first, second])


def _local_route(ctx: Context, method: AuthMethod) -> list[Step]:
    service = next((item for item in ctx.local_services if item.get("provider") == ctx.provider.id), None)
    if service and service.get("reachable"):
        models = len(service.get("models") or [])
        return [Step("server", "A server is answering", "done",
                     f"{service.get('url', '')} answered with {models} model(s) listed. A listing is not proof "
                     "that a model runs.", link=("Model routes", "/models"))]
    where = f" at {service['url']}" if service and service.get("url") else ""
    return [Step("server", "Start the server on this machine", "current",
                 f"No answer{where}. No credential is needed. " + (method.notes or ""))]


def _unavailable(ctx: Context, method: AuthMethod) -> list[Step]:
    meaning = STATUS_TEXT.get(method.status, (method.status, ""))[1]
    state = "blocked" if method.status in ("blocked", "retired") else "info"
    return [Step("status", CODE_LABELS.get(method.status, method.status).capitalize(), state,
                 (meaning + " " + (method.notes or "")).strip())]


_BUILDERS: dict[str, Callable[[Context, AuthMethod], list[Step]]] = {
    "api_key": _key_route, "custom_endpoint": _key_route, "cli_managed": _cli_route,
    "local_service": _local_route, **{kind: _sign_in_route for kind in _SIGN_IN},
}


def _steps_for(ctx: Context, method: AuthMethod) -> list[Step]:
    builder = _BUILDERS.get(method.type)
    if method.status not in _BUILT or builder is None:
        return _unavailable(ctx, method)
    return builder(ctx, method)


def route_guides(ctx: Context) -> list[RouteGuide]:
    """One guide per auth method, in the catalogue's order."""
    guides = []
    for method in ctx.provider.auth_methods:
        ids = [tid for tid, _ in _templates_for(ctx, method)]
        accounts = _accounts(ctx, ids)
        guides.append(RouteGuide(method=method, code_label=CODE_LABELS.get(method.status, method.status),
                                 accounts=tuple(accounts), focus=_focus(ctx, accounts),
                                 steps=tuple(_steps_for(ctx, method))))
    return guides
