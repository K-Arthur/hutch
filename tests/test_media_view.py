"""The media section's view models: routes, jobs and search come from data, with honest wording."""

from __future__ import annotations

from hutch.media.cost import load_prices
from hutch.media.providers.route_spec import load_routes
from hutch.media.status import service_status
from hutch.media.view import JOB_STATUS, _stamp, job_rows, price_text, route_rows, search_rows
from hutch.providers.catalog import bundled_catalog


def test_there_is_exactly_one_row_per_media_route_and_none_is_called_working():
    rows = route_rows()
    assert [row["id"] for row in rows] == list(load_routes())
    assert len({row["id"] for row in rows}) == len(rows)
    assert all(row["status_label"] != "works" for row in rows)       # no media route has a dated live run
    assert {row["status"] for row in rows} <= {"implemented-unverified", "documented", "blocked", "retired"}


def test_a_retired_or_unbuilt_route_is_labeled_as_such_with_its_reason():
    by_id = {row["id"]: row for row in route_rows()}
    retired = [row for row in by_id.values() if row["status"] == "retired"]
    assert retired and all("retired" in row["status_label"] for row in retired)
    assert all(row["notes"] for row in retired)


def test_price_text_states_the_basis_and_date_or_says_cost_unknown():
    priced = {key for key, row in load_prices().items() if row["basis"] != "unpriced"}
    assert priced
    for key in priced:
        text = price_text(key)
        assert text.startswith("about $") and "read 20" in text, (key, text)
    assert price_text("no-such-price-row").startswith("cost unknown")
    assert price_text("").startswith("cost unknown")


def test_every_route_with_no_readable_price_says_cost_unknown_never_a_number():
    prices = load_prices()
    for row in route_rows():
        has_price = prices.get(row["price_key"], {}).get("basis", "unpriced") != "unpriced"
        assert row["price"].startswith("cost unknown") != has_price, row["id"]
    assert any(row["price"].startswith("about $") for row in route_rows())      # and some are priced


def test_every_status_a_job_can_have_has_wording_and_the_unsafe_ones_say_so():
    seen = {service_status({"status": status, "error": error})
            for status in ("queued", "running", "succeeded", "failed", "cancelled")
            for error in ("", "refused: policy", "cancel_unconfirmed: no reply")}
    assert seen <= set(JOB_STATUS), seen - set(JOB_STATUS)
    assert "may still" in JOB_STATUS["cancel_unconfirmed"][2].lower() or "bill" in JOB_STATUS["cancel_unconfirmed"][2].lower()
    assert JOB_STATUS["refused"][0] == "refused" and "will not help" in JOB_STATUS["refused"][2]


def test_only_open_jobs_offer_actions_and_a_prompt_is_shown_truncated(store):
    from hutch.models import ApprovalMode, Bot, Run, RunStatus
    bot = Bot(name="media-view-bot", model="x/y", tools=[], approval_mode=ApprovalMode.ask)
    store.create_bot(bot)
    run = Run(bot_id=bot.id, prompt="p", status=RunStatus.running)
    store.create_run(run)
    with store._lock:
        for index, (status, error) in enumerate([("queued", None), ("running", None), ("succeeded", None),
                                                  ("failed", "refused: nope"), ("failed", "cancel_unconfirmed: x")]):
            store._db.execute(
                "INSERT INTO media_jobs (id, run_id, conversation_id, kind, backend, status, requested, "
                "created_at, updated_at, error, idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (f"mj_{index:016x}", run.id, run.conversation_id, "image", "fake", status,
                 '{"prompt": "' + "x" * 400 + '"}', "2026-11-06T00:00:00Z", "2026-11-06T00:00:00Z", error, f"k{index}"))
        store._db.commit()
    rows = {row["status"]: row for row in job_rows(store, finished=True)}
    assert {name for name, row in rows.items() if row["can_act"]} == {"submitting", "running"}
    assert all(len(row["prompt_preview"]) <= 200 for row in rows.values())
    assert [row["status"] for row in job_rows(store, finished=False)].count("succeeded") == 0


def test_search_rows_list_only_providers_with_a_built_search_route():
    rows = search_rows(bundled_catalog())
    assert rows and all(row["template"] and row["provider"] for row in rows)
    assert {row["provider"] for row in rows} == {"xiaomi"} or all(row["status"] for row in rows)


def test_a_timestamp_is_shown_to_the_minute_in_utc():
    assert _stamp("2026-11-07T02:27:06.925178+00:00") == "2026-11-07 02:27 UTC"
    assert _stamp(None) == "" and _stamp("short") == "short"
