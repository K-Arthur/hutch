from datetime import datetime, timedelta, timezone

import pytest

from hutch import route_readiness as rr
from hutch.providers.base import ProviderError

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("kind,status,state", [
    ("unreachable", None, rr.UNREACHABLE),
    ("timeout", None, rr.TIMED_OUT),
    ("auth", 401, rr.INVALID_CREDENTIAL),
    ("auth", None, rr.INVALID_CREDENTIAL),
    ("auth", 403, rr.PERMISSION_DENIED),
    ("quota", 402, rr.NO_CREDIT),
    ("rate_limit", 429, rr.RATE_LIMITED),
    ("server", 503, rr.UNAVAILABLE),
    ("stream", None, rr.UNAVAILABLE),
    ("oom", 500, rr.UNAVAILABLE),
    ("refused", None, rr.UNAVAILABLE),
    ("other", None, rr.UNAVAILABLE),
    ("bad_request", 400, rr.INVALID_ROUTE),
    ("model_missing", 404, rr.MODEL_MISSING),
    ("context", 400, rr.CONTEXT_OR_INCOMPLETE),
    ("incomplete", None, rr.CONTEXT_OR_INCOMPLETE),
])
def test_every_provider_kind_has_a_canonical_state(kind, status, state):
    assert rr.classify(kind, http_status=status) == state


def test_all_provider_error_kinds_are_covered_and_unknown_is_not_a_bare_error():
    for kind in ProviderError.KINDS:
        assert rr.classify(kind).startswith("provider.")
    assert rr.classify("brand-new-kind") == rr.UNAVAILABLE


def test_metadata_success_is_never_verified_and_only_generation_is():
    meta = rr.metadata_result(["m1", "m2"], "authenticated", NOW)
    assert meta.state == rr.SAVED_UNVERIFIED and meta.mode == rr.MODE_METADATA
    assert meta.models == ("m1", "m2")
    gen = rr.generation_result("m1", "ready", NOW)
    assert gen.state == rr.VERIFIED and gen.mode == rr.MODE_GENERATION


def test_no_state_token_is_a_bare_error():
    for name in dir(rr):
        value = getattr(rr, name)
        if name.isupper() and isinstance(value, str) and "." in value:
            assert value.split(".", 1)[1] != "error"


def test_retry_policy_only_allows_transient_states():
    for state in (rr.RATE_LIMITED, rr.TIMED_OUT, rr.UNAVAILABLE, rr.UNREACHABLE):
        assert rr.retry_allowed(state)
    for state in (rr.INVALID_CREDENTIAL, rr.PERMISSION_DENIED, rr.NO_CREDIT,
                  rr.INVALID_ROUTE, rr.MODEL_MISSING, rr.CONTEXT_OR_INCOMPLETE,
                  rr.SAVED_UNVERIFIED, rr.VERIFIED):
        assert not rr.retry_allowed(state)


def test_retry_after_is_capped_and_counts_down_on_a_fixed_clock():
    result = rr.failure_result("rate_limit", mode=rr.MODE_METADATA, detail="slow down",
                               now=NOW, http_status=429, retry_after=120)
    assert rr.retry_in_seconds(result, NOW) == 120
    assert rr.retry_in_seconds(result, NOW + timedelta(seconds=90)) == 30
    assert rr.retry_in_seconds(result, NOW + timedelta(seconds=121)) == 0
    assert rr.display_state(result, NOW) == rr.RETRY_SCHEDULED
    assert rr.display_state(result, NOW + timedelta(seconds=200)) == rr.RATE_LIMITED
    huge = rr.failure_result("rate_limit", mode=rr.MODE_METADATA, detail="", now=NOW, retry_after=99999)
    assert rr.retry_in_seconds(huge, NOW) == rr.RETRY_AFTER_CAP_SECONDS
    missing = rr.failure_result("rate_limit", mode=rr.MODE_METADATA, detail="", now=NOW)
    assert rr.retry_in_seconds(missing, NOW) == rr.DEFAULT_RETRY_SECONDS
    other = rr.failure_result("server", mode=rr.MODE_METADATA, detail="", now=NOW)
    assert rr.retry_in_seconds(other, NOW) == 0


def test_snapshots_go_stale_and_old_success_is_not_replayed():
    gen = rr.generation_result("m", "ready", NOW)
    assert not rr.is_stale(gen, NOW + timedelta(seconds=rr.SNAPSHOT_TTL_SECONDS - 1))
    assert rr.is_stale(gen, NOW + timedelta(seconds=rr.SNAPSHOT_TTL_SECONDS + 1))
    assert rr.revalidation_required(None, NOW)
    assert rr.revalidation_required(gen, NOW + timedelta(hours=1))
    assert not rr.revalidation_required(gen, NOW)


def test_safe_detail_redacts_the_key_and_bounds_length():
    secret = "sk-live-abcdef123456"
    out = rr.safe_detail(f"bad key {secret} rejected", secret)
    assert secret not in out and "[key]" in out
    long = rr.safe_detail("x" * 5000)
    assert len(long) <= rr.DETAIL_LIMIT
    assert rr.safe_detail(None) == ""


def test_module_is_pure():
    import ast
    import pathlib
    tree = ast.parse(pathlib.Path(rr.__file__).read_text())
    names = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(x.split(".")[0] in {"fastapi", "starlette", "httpx", "requests", "sqlite3", "jinja2"}
                   for x in names)
