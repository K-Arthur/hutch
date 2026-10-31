"""Provider-native search route declaration and wire rules (chat-completions web search).

This module answers two questions with no network: what a connection's template declares, and
what a provider reply means. The transport lives in
:mod:`hutch.providers.search`, so the rules here are testable without a client.

Wire contract, read from the vendor's own documentation on 2026-10-31
(https://mimo.mi.com/static/docs/quick-start/usage-guide/text-generation/tool-calling/web-search.md):

    POST {base_url}/chat/completions
    {"model": "mimo-v2.6-pro",
     "messages": [{"role": "user", "content": "<the query>"}],
     "tools": [{"type": "web_search", "max_keyword": 3, "force_search": true, "limit": 1}],
     "tool_choice": "auto"}

The reply is an ordinary chat completion. The answer is ``choices[0].message.content`` and
the sources are ``choices[0].message.annotations[]`` entries with ``type == "url_citation"``
(``url``, ``title``, ``summary``, ``site_name``, ``publish_time``). Search billing is
reported separately as ``usage.web_search_usage = {tool_usage, page_usage}``: one search
round can fan out to several keywords, so ``tool_usage`` counts billable plugin calls, not
queries.

Honesty rules encoded here rather than left to callers:

* an empty answer is an error, never an empty success;
* a missing ``web_search_usage`` is reported as *unreported*, never as zero - a zero would
  read as a free request, and the plugin is explicitly billed per call;
* a reply with no citations and no search usage is reported as "the provider did not
  search", because the vendor documents exactly that failure mode: the model may decide
  the query needs no search, and an ungrounded answer must not be presented as grounded;
* annotation types Hutch does not understand are counted and reported, never dropped in
  silence;
* citation URLs are treated as untrusted data: only absolute http(s) links are reported,
  and nothing is fetched;
* a reply from a different model id is reported, so a silent substitution is visible.

The vendor documents this plugin as OpenAI Chat Completions only, requires it to be
activated in the account's console first, and lists ``mimo-v2.6-flash``, ``mimo-v2.6-pro``
and ``mimo-v2.6-pro-ultraspeed`` as the supporting models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlsplit

#: Documented models for the web-search plugin (vendor page read 2026-10-31). Recorded here
#: as the vendor's claim; Hutch does not refuse another model on the vendor's behalf.
SEARCH_MODELS = ("mimo-v2.6-flash", "mimo-v2.6-pro", "mimo-v2.6-pro-ultraspeed")

#: Hutch's own bounds, not vendor claims: they cap what one tool call may ask for.
MAX_QUERY_CHARS = 2000
MAX_MAX_KEYWORD = 8
MAX_RESULTS_PER_KEYWORD = 10
MAX_CITATIONS = 40
MAX_ANSWER_CHARS = 200_000

_SUPPORTED_PROTOCOL = "chat-web-search"
_ALLOWED_SCHEMES = ("http", "https")


# ------------------------------------------------------------------ route


class SearchError(RuntimeError):
    """The search request was refused or failed; the message names the provider's reason."""


@dataclass(frozen=True)
class SearchRoute:
    """What one connection's template declares about its provider-native search."""

    model: str
    max_keyword: int = 3
    results_per_keyword: int = 1
    force_search: bool = True
    source: str = ""


def route_from_template(template: Optional[dict[str, Any]]) -> Optional[SearchRoute]:
    """Read and validate the optional ``search`` block of a connection template.

    ``None`` means the route is not offered. A malformed block raises ``ValueError`` so a
    configuration mistake is loud rather than silently disabling the capability.
    """
    if not template:
        return None
    block = template.get("search")
    if block is None:
        return None
    if not isinstance(block, dict):
        raise ValueError("search must be a JSON object")
    protocol = block.get("protocol", _SUPPORTED_PROTOCOL)
    if protocol != _SUPPORTED_PROTOCOL:
        raise ValueError(f"unsupported search protocol {protocol!r}")
    model = block.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > 160:
        raise ValueError("search.model must be a non-empty model id")
    max_keyword = block.get("max_keyword", 3)
    if isinstance(max_keyword, bool) or not isinstance(max_keyword, int) \
            or not 1 <= max_keyword <= MAX_MAX_KEYWORD:
        raise ValueError(f"search.max_keyword must be an integer 1-{MAX_MAX_KEYWORD}")
    limit = block.get("results_per_keyword", 1)
    if isinstance(limit, bool) or not isinstance(limit, int) \
            or not 1 <= limit <= MAX_RESULTS_PER_KEYWORD:
        raise ValueError(
            f"search.results_per_keyword must be an integer 1-{MAX_RESULTS_PER_KEYWORD}")
    force = block.get("force_search", True)
    if not isinstance(force, bool):
        raise ValueError("search.force_search must be true or false")
    source = block.get("source", "")
    if source and (not isinstance(source, str) or not source.startswith("https://")):
        raise ValueError("search.source must be an https URL when present")
    return SearchRoute(model=model.strip(), max_keyword=max_keyword,
                       results_per_keyword=limit, force_search=force, source=source)


# ------------------------------------------------------------------ wire


@dataclass(frozen=True)
class Citation:
    """One provider-supplied source. Never fetched, never rewritten."""

    url: str
    title: str = ""
    site_name: str = ""
    summary: str = ""
    published: str = ""


@dataclass(frozen=True)
class SearchResult:
    answer: str
    citations: tuple[Citation, ...]
    model: str                    # the model id the provider says answered
    requested_model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    search_calls: Optional[int] = None      # None = the provider did not report it
    page_usage: Optional[int] = None
    dropped_annotations: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def substituted_model(self) -> bool:
        return bool(self.model) and self.model != self.requested_model

    @property
    def searched(self) -> bool:
        """Whether the provider shows any evidence of having searched.

        A citation or a reported plugin call is evidence. Absence of both is the
        documented "the model decided not to search" case, and it is not grounding.
        """
        return bool(self.citations) or bool(self.search_calls)


def build_payload(route: SearchRoute, query: str) -> dict[str, Any]:
    """The exact request body for one provider-native search."""
    clean = " ".join(str(query or "").split())
    if not clean:
        raise SearchError("there is no query to search for")
    if len(clean) > MAX_QUERY_CHARS:
        raise SearchError(
            f"the query is {len(clean)} characters; Hutch sends at most {MAX_QUERY_CHARS}")
    tool: dict[str, Any] = {
        "type": "web_search",
        "max_keyword": route.max_keyword,
        "force_search": route.force_search,
        "limit": route.results_per_keyword,
    }
    return {
        "model": route.model,
        "messages": [{"role": "user", "content": clean}],
        "tools": [tool],
        "tool_choice": "auto",
    }


def _int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))


def _optional_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, int(value))


def _safe_url(value: Any) -> str:
    """Report only an absolute http(s) URL. Anything else is dropped, not repaired."""
    if not isinstance(value, str) or not value.strip():
        return ""
    raw = value.strip()
    if len(raw) > 2048:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme.lower() not in _ALLOWED_SCHEMES or not parts.netloc:
        return ""
    return raw


def _citation(entry: dict[str, Any]) -> Optional[Citation]:
    url = _safe_url(entry.get("url"))
    if not url:
        return None

    def text(key: str, limit: int) -> str:
        value = entry.get(key)
        return " ".join(str(value).split())[:limit] if isinstance(value, str) else ""

    return Citation(url=url, title=text("title", 300), site_name=text("site_name", 120),
                    summary=text("summary", 600), published=text("publish_time", 40))


def parse_search_response(body: Any, route: SearchRoute) -> SearchResult:
    """Turn a provider reply into an answer plus sources, or raise when it is not an answer."""
    if not isinstance(body, dict):
        raise SearchError("the search endpoint did not return a JSON object")
    if body.get("error"):
        error = body["error"]
        detail = error.get("message") if isinstance(error, dict) else error
        raise SearchError(f"the search endpoint reported an error: {detail}")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise SearchError("the search endpoint returned no choices")
    choice = choices[0]
    message = choice.get("message") or {}
    answer = message.get("content") if isinstance(message, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        raise SearchError(
            "the search endpoint returned no answer text; Hutch does not report an empty "
            "reply as a successful search")

    raw_annotations = message.get("annotations") if isinstance(message, dict) else None
    citations: list[Citation] = []
    dropped = 0
    if isinstance(raw_annotations, list):
        for entry in raw_annotations:
            if not isinstance(entry, dict) or entry.get("type") != "url_citation":
                dropped += 1
                continue
            citation = _citation(entry)
            if citation is None:
                dropped += 1
                continue
            if len(citations) >= MAX_CITATIONS:
                dropped += 1
                continue
            citations.append(citation)

    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    web = usage.get("web_search_usage") if isinstance(usage.get("web_search_usage"), dict) else None
    search_calls = _optional_int(web.get("tool_usage")) if web else None
    page_usage = _optional_int(web.get("page_usage")) if web else None
    answered_model = body.get("model") if isinstance(body.get("model"), str) else ""

    notes: list[str] = []
    if answered_model and answered_model != route.model:
        notes.append(f"requested {route.model}, and the provider answered with {answered_model}")
    if web is None:
        notes.append(
            "the provider did not report web-search usage, so the number of billed search "
            "calls for this reply is unknown (not zero)")
    if not citations and search_calls in (None, 0):
        notes.append(
            "the provider returned no citations and reported no search call, so this answer "
            "is not grounded in a web search, whatever the prompt asked for")
    if dropped:
        notes.append(
            f"{dropped} annotation(s) were not usable url_citation entries and are not shown")
    finish = choice.get("finish_reason")
    if finish == "length":
        notes.append("the provider stopped at its output limit; the answer may be truncated")
    return SearchResult(
        answer=answer.strip()[:MAX_ANSWER_CHARS],
        citations=tuple(citations),
        model=answered_model or route.model,
        requested_model=route.model,
        prompt_tokens=_int(usage.get("prompt_tokens")),
        completion_tokens=_int(usage.get("completion_tokens")),
        search_calls=search_calls,
        page_usage=page_usage,
        dropped_annotations=dropped,
        notes=tuple(notes),
    )


__all__ = ["Citation", "MAX_ANSWER_CHARS", "MAX_CITATIONS", "MAX_MAX_KEYWORD",
           "MAX_QUERY_CHARS", "MAX_RESULTS_PER_KEYWORD", "SEARCH_MODELS", "SearchError",
           "SearchResult", "SearchRoute", "build_payload", "parse_search_response",
           "route_from_template"]
