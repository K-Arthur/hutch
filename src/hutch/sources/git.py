"""Git source: ref-change detection via bounded, read-only git plumbing.

The cursor stores the last observed commit and the ref it came from. Nothing
here fetches, pulls, or writes to the repository. History rewrites (rebase,
force-push, reset) are reported as one ``history_rewritten`` event rather than
pretending the old commit range still exists.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import CheckOutcome, EventDraft, SourceRuntime, SourceUnavailable

_GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "LC_ALL": "C",
}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _git(path: Path, args: list[str], *, timeout: float) -> str:
    env = {**os.environ, **_GIT_ENV}
    try:
        result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True,
                                timeout=timeout, check=False, env=env)
    except FileNotFoundError as exc:
        raise SourceUnavailable("git is not installed on this machine") from exc
    except subprocess.TimeoutExpired as exc:
        raise SourceUnavailable(f"git did not answer within {timeout:.0f}s") from exc
    if result.returncode != 0:
        detail = " ".join(((result.stderr or result.stdout) or "").split())[:200]
        raise SourceUnavailable(detail or f"git {' '.join(args)} failed")
    return result.stdout


def check(config: dict, cursor: dict, *, runtime: SourceRuntime, now: datetime) -> CheckOutcome:
    raw_path = str(config.get("path") or "").strip()
    path = Path(raw_path).expanduser()
    if not raw_path or not path.is_absolute():
        raise SourceUnavailable("the repository path must be an absolute path")
    if not path.is_dir():
        raise SourceUnavailable(f"the repository is not available: {path}")
    ref = str(config.get("ref") or "HEAD").strip() or "HEAD"
    max_commits = max(1, min(int(config.get("max_commits") or 50), 200))
    timeout = max(2.0, min(float(runtime.timeout), 60.0))

    head = _git(path, ["rev-parse", "--verify", f"{ref}^{{commit}}"], timeout=timeout).strip()
    if not head:
        raise SourceUnavailable(f"ref {ref!r} does not resolve to a commit")

    previous = str(cursor.get("head") or "")
    old_ref = str(cursor.get("ref") or ref)
    new_cursor = {"head": head, "ref": ref}
    if not previous:
        return CheckOutcome(cursor=new_cursor, events=(),
                            summary=f"first check established the baseline at {head[:12]}")
    if previous == head:
        return CheckOutcome(cursor=new_cursor, events=(), summary="no change")

    ancestor = subprocess.run(["git", "-C", str(path), "merge-base", "--is-ancestor", previous, head],
                              capture_output=True, text=True, timeout=timeout, check=False, env={**os.environ, **_GIT_ENV})
    if ancestor.returncode != 0:
        return CheckOutcome(
            cursor=new_cursor,
            events=(EventDraft(key=head, kind="history_rewritten", occurrence=_iso(now.timestamp()),
                               content_hash=head,
                               summary=f"history was rewritten or force-pushed: {old_ref} moved from "
                                       f"{previous[:12]} to {head[:12]}").normalized(),),
            summary=f"history rewritten: {previous[:12]} -> {head[:12]}")

    count_raw = _git(path, ["rev-list", "--count", f"{previous}..{head}"], timeout=timeout).strip()
    try:
        total = int(count_raw)
    except ValueError:
        total = 0
    raw = _git(path, ["log", f"--format=%H%x1f%ct%x1f%s", f"--max-count={max_commits}", f"{previous}..{head}"],
               timeout=timeout)
    events: list[EventDraft] = []
    for line in raw.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        sha, stamp, subject = parts
        try:
            when = _iso(float(stamp))
        except ValueError:
            when = _iso(now.timestamp())
        events.append(EventDraft(key=sha, kind="new_items", occurrence=when, content_hash=sha,
                                 summary=f"commit {sha[:12]}: {' '.join(subject.split())[:200]}").normalized())
    return CheckOutcome(cursor=new_cursor, events=tuple(events),
                        summary=(f"{len(events)} new commit(s) on {ref}" + (" (older commits elided)" if total > len(events) else "")),
                        truncated=total > len(events))
