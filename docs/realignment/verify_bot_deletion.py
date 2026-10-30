#!/usr/bin/env python3
"""Real-world exercise of governed whole-Bot permanent deletion (run-3 evidence).

The command-layer behaviour is unit-tested in `tests/test_bot_deletion.py`; this
script exercises the same path on a disposable state directory with two Bots that
hold realistic records and managed files. It proves, from outside the test suite,
that one Bot can be deleted while the other stays intact, that managed files are
removed while user-owned paths survive, that retained rows are content-free, and
that a post-deletion retry replays instead of double-erasing.

The runs are seeded records, not live model executions: no provider, engine worker
or process is involved, so this is state-layer evidence, not a live-agent run.

Usage:
    .venv/bin/python docs/realignment/verify_bot_deletion.py

Exit code 0 only when every check passes; a JSON receipt is written outside the
state directory and its path is printed.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys
import tempfile
import uuid

CHECKS: list[str] = []


def check(condition: object, message: str) -> None:
    """Record one real-world assertion; abort the script with a clear reason."""
    if not condition:
        raise AssertionError(message)
    CHECKS.append(message)


def iso_now() -> str:
    """Timestamp format used by the store (ISO-8601 UTC)."""
    from hutch.models import iso, utcnow
    return iso(utcnow())


def insert_message(store, conversation_id: str, run_id: str, content: str) -> str:
    """Insert one stored message plus its search row (the shape the engine writes)."""
    message_id = "msg_" + uuid.uuid4().hex[:16]
    with store._tx() as db:
        db.execute("INSERT INTO messages (id, conversation_id, seq, run_id, role, content, created_at) "
                   "VALUES (?, ?, 1, ?, 'user', ?, ?)",
                   (message_id, conversation_id, run_id, content, iso_now()))
        db.execute("INSERT INTO conversation_fts (message_id, conversation_id, content) "
                   "VALUES (?, ?, ?)", (message_id, conversation_id, content))
    return message_id


def seed_bot(store, cfg, slug: str) -> dict:
    """Create one Bot with a conversation, finished run, event, stored message, fact and files."""
    from hutch.models import Bot, Event, EventType, Run, RunStatus
    bot = store.create_bot(Bot(name=slug, display_name=slug.replace('-', ' ').title()))
    conversation, _ = store.create_conversation(
        bot.id, f"{slug} chat", idem_key=f"{slug}-chat", request_hash=f"{slug}-chat-hash")
    run = store.create_run(Run(bot_id=bot.id, conversation_id=conversation["id"],
                               prompt=f"{slug} prompt", status=RunStatus.succeeded,
                               finished_at=iso_now(), exit_reason="completed"))
    store.append_event(Event(run_id=run.id, type=EventType.message,
                             data={"text": f"transcript sentinel{slug.replace('-', '')}"}))
    store.flush_events()  # the writer is asynchronous; the preview counts canonical rows
    store.remember(bot.id, f"{slug}-fact", f"sentinel-value-{slug}",
                   conversation_id=conversation["id"])
    message_id = insert_message(store, conversation["id"], run.id,
                                f"sentinel{slug.replace('-', '')}")
    run_dir = cfg.ensure_run_workspace(bot.name, run.id)
    (run_dir / "artifact.txt").write_text(f"managed artifact for {slug}", encoding="utf-8")
    managed = cfg.ensure_managed_workspace(bot.id)
    (managed / "note.txt").write_text("managed workspace note", encoding="utf-8")
    profile = cfg.browser_profile_dir(bot.id)
    (profile / "profile.json").write_text("{}", encoding="utf-8")
    return {
        "bot": bot,
        "conversation": conversation,
        "run": run,
        "message_id": message_id,
        "paths": {
            "run_dir": cfg.run_dir(bot.name, run.id),
            "managed": managed,
            "profile_root": cfg.state_dir / "browser-profiles" / bot.id,
        },
    }


def snapshot(store, seeded: dict) -> dict:
    """Count the second Bot's linked rows so untouched-ness is provable."""
    bot_id = seeded["bot"].id
    with store._lock:
        rows = store._db.execute(
            "SELECT (SELECT COUNT(*) FROM bots WHERE id = ?), "
            "(SELECT COUNT(*) FROM conversations WHERE bot_id = ?), "
            "(SELECT COUNT(*) FROM runs WHERE bot_id = ?), "
            "(SELECT COUNT(*) FROM memory_facts WHERE bot_id = ?), "
            "(SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id "
            " WHERE c.bot_id = ?)",
            (bot_id, bot_id, bot_id, bot_id, bot_id)).fetchone()
    return {"counts": tuple(rows), "files": tuple(
        str(path) for path in seeded["paths"].values())}


def query_one(store, sql: str, args: tuple = ()):
    """One scalar query against the verification store."""
    with store._lock:
        return store._db.execute(sql, args).fetchone()[0]


def query_rows(store, sql: str, args: tuple = ()) -> list[tuple]:
    """All rows of one verification query as plain tuples."""
    with store._lock:
        return [tuple(row) for row in store._db.execute(sql, args).fetchall()]


def sealed_state(store) -> None:
    """Check retained audit evidence cannot be rewritten afterwards."""
    import sqlite3
    record = query_rows(store, "SELECT id FROM bot_deletions LIMIT 1")
    try:
        with store._tx() as db:
            db.execute("DELETE FROM bot_deletions")
    except sqlite3.IntegrityError:
        CHECKS.append("deletion evidence refuses to be deleted")
    else:
        raise AssertionError("deletion evidence was deletable: " + repr(record))


def main() -> int:
    """Run every real-world check and print the receipt path."""
    state = pathlib.Path(tempfile.mkdtemp(prefix="hutch-bot-deletion-verify-"))
    os.environ["HUTCH_STATE_DIR"] = str(state)
    from hutch import bot_deletion
    from hutch.config import get_config
    from hutch.models import Run
    from hutch.store import Store

    config = get_config()
    config.ensure()
    store = Store(config)
    try:
        alpha = seed_bot(store, config, "verify-alpha")
        beta = seed_bot(store, config, "verify-beta")
        gamma = seed_bot(store, config, "verify-gamma")
        # A live run must block deletion and request cancellation, never erase.
        live = store.create_run(Run(bot_id=gamma["bot"].id, prompt="still running"))
        user_owned = state / "user-owned"
        user_owned.mkdir()
        (user_owned / "keep.txt").write_text("operator file", encoding="utf-8")
        outside = pathlib.Path(tempfile.mkdtemp(prefix="hutch-verify-workdir-"))
        (outside / "keep.txt").write_text("folder-mode workdir", encoding="utf-8")
        code_worktree = state / "code-worktrees" / "handoff-verify"
        code_worktree.mkdir(parents=True)
        (code_worktree / "keep.patch").write_text("user coding work", encoding="utf-8")
        beta_before = snapshot(store, beta)

        preview = bot_deletion.preview(store, alpha["bot"].id, actor="verify-script",
                                       note="real-world exercise")
        check(preview["confirmation_hint"] == "verify-alpha", "preview names the typed Bot address")
        check(preview["counts"].get("bot") == 1, "preview counts the Bot row")
        check(preview["counts"].get("runs", 0) >= 1, "preview counts the stored runs")
        check(preview["counts"].get("files", 0) >= 3, "preview counts the managed files")
        check(len(preview["token"]) >= 16, "preview issues a one-time token")
        token_hash = query_one(store, "SELECT token_hash FROM bot_deletions WHERE id = ?",
                               (preview["request_id"],))
        check(token_hash == hashlib.sha256(preview["token"].encode()).hexdigest(),
              "the preview stores the token only as a hash")
        check(token_hash != preview["token"], "the plaintext token is not stored")

        for label, kwargs in (
            ("wrong typed address", {"token": preview["token"], "confirmation": "verify-beta"}),
            ("wrong token", {"token": "x" * 32, "confirmation": "verify-alpha"}),
        ):
            try:
                bot_deletion.confirm(store, alpha["bot"].id, preview["request_id"],
                                     actor="verify-script", idem_key=f"bad-{label}",
                                     request_hash=hashlib.sha256(label.encode()).hexdigest(),
                                     **kwargs)
            except bot_deletion.BotDeletionConflict:
                CHECKS.append(f"{label} fails closed")
            else:
                raise AssertionError(f"{label} was accepted")
        check(store.get_bot("verify-alpha") is not None, "refused confirmations erase nothing")
        check(alpha["paths"]["run_dir"].exists(), "refused confirmations keep managed files")

        try:
            bot_deletion.preview(store, gamma["bot"].id, actor="verify-script")
        except bot_deletion.BotDeletionConflict:
            CHECKS.append("a live run blocks preview and asks the operator to stop it")
        else:
            raise AssertionError("a live run did not block deletion preview")
        check(store.get_run(live.id) is not None, "the live run is not killed implicitly")

        idem_key = "verify-real-world-1"
        request_hash = hashlib.sha256(b"verify-real-world").hexdigest()
        result = bot_deletion.confirm(store, alpha["bot"].id, preview["request_id"],
                                      token=preview["token"], confirmation="verify-alpha",
                                      actor="verify-script", idem_key=idem_key,
                                      request_hash=request_hash)
        check(result["status"] == "confirmed", "confirmation reports a confirmed deletion")
        check(result["cleanup_state"] in ("cleaned", "needs_attention"),
              "confirmation reports the cleanup outcome")
        check(store.get_bot("verify-alpha") is None, "the deleted Bot no longer resolves")
        check(store.get_run(alpha["run"].id) is None, "the deleted Bot's runs are erased")
        check(query_one(store, "SELECT COUNT(*) FROM conversations WHERE bot_id = ?",
                        (alpha["bot"].id,)) == 0, "the deleted Bot's conversations are erased")
        check(query_one(store, "SELECT COUNT(*) FROM memory_facts WHERE bot_id = ? "
                               "AND (value != '' OR purged_at = '')",
                        (alpha["bot"].id,)) == 0,
              "the deleted Bot's fact revisions are content-free tombstones")
        check(query_one(store, "SELECT COUNT(*) FROM messages WHERE content LIKE ?",
                        ("%sentinelverifyalpha%",)) == 0, "the deleted Bot's messages are erased")
        check(query_one(store, "SELECT COUNT(*) FROM conversation_fts "
                               "WHERE conversation_fts MATCH 'sentinelverifyalpha'") == 0,
              "the deleted Bot's transcript search rows are gone")
        check(query_one(store, "SELECT COUNT(*) FROM memory_facts_fts WHERE rowid IN "
                               "(SELECT rowid FROM memory_facts WHERE bot_id = ?)",
                        (alpha["bot"].id,)) == 0,
              "the deleted Bot's memory search rows are gone")
        check(not alpha["paths"]["run_dir"].exists(), "managed run directory removed")
        check(not alpha["paths"]["managed"].exists(), "managed workspace removed")
        check(not alpha["paths"]["profile_root"].exists(), "browser profile removed")
        check((user_owned / "keep.txt").exists(), "a user-owned state subdirectory survives")
        check((outside / "keep.txt").exists(), "a folder-mode workdir survives")
        check((code_worktree / "keep.patch").exists(), "a coding handoff worktree survives")

        check(store.get_bot("verify-beta") is not None, "the second Bot still exists")
        check(store.get_run(beta["run"].id) is not None, "the second Bot's run still exists")
        check(beta["paths"]["run_dir"].exists(), "the second Bot's managed files still exist")
        check(snapshot(store, beta) == beta_before, "the second Bot's rows are unchanged")
        check(store.search_conversation_messages("sentinelverifybeta",
                                                 bot_id=beta["bot"].id),
              "the second Bot's transcript is still searchable")

        row_blob = json.dumps(query_rows(store, "SELECT * FROM bot_deletions", ()), default=str)
        item_blob = json.dumps(query_rows(store, "SELECT * FROM bot_deletion_items", ()), default=str)
        for needle in ("sentinel", "verify-alpha", str(state), str(outside)):
            check(needle not in row_blob, f"request evidence has no {needle!r} content")
            check(needle not in item_blob, f"item evidence has no {needle!r} content")
        check(query_one(store, "SELECT COUNT(*) FROM bot_deletion_items WHERE request_id = ?",
                        (preview["request_id"],)) > 0, "the erase wrote content-free item evidence")

        record = bot_deletion.request_record(store, preview["request_id"])
        check(record is not None and record["status"] == "confirmed",
              "request_record resolves a confirmed request without the Bot row")
        check("token" not in record, "request_record never returns a token")
        history = bot_deletion.requests(store, alpha["bot"].id)
        check(len(history) == 1 and history[0]["status"] == "confirmed",
              "content-free history remains queryable by the recorded Bot id")
        check("token" not in history[0], "history never returns a token")

        replay = bot_deletion.confirm(store, alpha["bot"].id, preview["request_id"],
                                      token=preview["token"], confirmation="verify-alpha",
                                      actor="verify-script", idem_key=idem_key,
                                      request_hash=request_hash)
        check(replay == result, "an exact retry after deletion replays the stored result")
        try:
            bot_deletion.confirm(store, alpha["bot"].id, preview["request_id"],
                                 token=preview["token"], confirmation="verify-alpha",
                                 actor="verify-script", idem_key="different-command",
                                 request_hash=hashlib.sha256(b"different").hexdigest())
        except bot_deletion.BotDeletionConflict:
            CHECKS.append("a different retry is refused instead of erasing twice")
        else:
            raise AssertionError("a different retry was accepted after deletion")
        check(any("backup" in line.lower() or "provider" in line.lower()
                  for line in result["remaining"]),
              "the result states what permanent deletion cannot retract")
        sealed_state(store)
        recovery = bot_deletion.recover_cleanup(store)
        check(isinstance(recovery, dict), "cleanup recovery returns a summary")
        check(query_one(store, "SELECT COUNT(*) FROM bot_deletions "
                               "WHERE cleanup_state IN ('pending','cleaning')") == 0,
              "no committed deletion is left with pending cleanup")

        receipt = {
            "state_dir": str(state),
            "preview_counts": preview["counts"],
            "result_counts": result["counts"],
            "cleanup_state": result["cleanup_state"],
            "checks": CHECKS,
        }
        receipt_path = pathlib.Path(tempfile.mkdtemp(prefix="hutch-verify-receipt-")) / "receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(f"PASS {len(CHECKS)} checks")
        print(f"receipt: {receipt_path}")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as failure:
        print(f"FAIL {failure}")
        sys.exit(1)
