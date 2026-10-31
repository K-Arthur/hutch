# Computer use and automation: what was decided, and why

This record closes the loop on the research in [research.md](research.md). For each recommendation it states what was done,
what was already true in this checkout, and what was deliberately not done. Claims about behaviour point at the code and the
tests that exercise it; claims about the wider field point at the numbered sources (S-IDs) in `research.md`.

Nothing here is a roadmap promise. A recommendation that was not implemented says so and says what would be needed.

## 1. Route stale coordinates through a bounded frame ceiling

**Adopted.** `computer/frames.py` now refuses a frame whose long edge exceeds 1568 px, which is the documented long-edge
limit of the supported vision routes (S1, S3). The browser viewport (1280x720, Playwright's default for a persistent context)
and the isolated desktop (1280x800) already fit inside it, so the ceiling is a backstop rather than a resize step. A provider
that silently downscales a larger image would move every coordinate a model reports; refusing the oversized frame removes
that failure class instead of compensating for it.

**Not adopted:** a per-route resize-and-record step. It is only needed if a supported route's limit is ever lower than a
capture size, and no supported route is today. The measurement in research.md §1 (1,000-1,800 tokens per screenshot) argues
for keeping captures small, not for adding a transform.

## 2. Give the native path addressable references instead of coordinates

**Adopted, with a different mechanism than the recommendation.** The recommendation was much cheaper than expected because
the interface already existed: AT-SPI exposes roles, names, text and actions. An isolated KWin session now starts a private
accessibility bus (`native/a11y_bus.py`), applications receive exactly one additional read-only socket mount for it, and an
out-of-process worker (`native/a11y_worker.py`, run under a PyGObject interpreter because Hutch's own has no GTK bindings)
reads a bounded tree. `computer elements` / `activate` / `set_text` act on element ids, fenced to the snapshot that issued
them (`computer/accessibility.py`, `computer/a11y_tree.py`).

Verified on the reference host: KWrite's text was replaced and its toolbar Save button pressed by accessible name; the file
on disk contained the new text. No coordinates, no image model. Covered by `tests/e2e/test_computer_semantic_native.py`
(no coordinate appears anywhere in that file) and pinned without a desktop by `tests/test_computer_semantic.py`.

**The benchmark is honest about the cost.** `benchmarks/computer_semantic_ab.py` runs one task both ways: 4 calls and
`effect_verified` versus 5 calls and `visual_change_only`; zero images versus five frames of 99.7 KB; but 11.2k characters of
tree text against 281 characters of observation summaries. There is no model in that loop, so it is not an accuracy claim.

**Sequencing note.** Research recommendation 8 asked for a measured bake-off before making a tree the default. That is what
this is: a measured comparison on Hutch's own task, with the pixel path kept and documented as the fallback. The tree is not
the default — the model chooses, and `elements` is offered first in the tool description only because it is usually cheaper
in steps. OSWorld-style evidence that most leaderboard entries use no tree is about *research harnesses* run against one
operating system, not about whether a KDE application can be driven by its own control names; both are recorded.

## 3. Move confirmation for consequential actions before dispatch

**Already partly true; not extended.** Hutch's `ApprovalGate` already refuses to make *outward* actions sticky and already
asks for the computer session and each launch (`src/hutch/tools/computer.py`). The research proposes a classifier over button
labels and hosts to force approval even when a sticky rule would allow an action (S10, S12).

**Not adopted in this pass,** for two reasons that are worth recording rather than hiding: the measured benefit is a recall
figure from a vendor's own evaluation (92% on 607 tasks, S10) which says nothing about its precision on Hutch's traffic, and
a noisy classifier converts a working approval flow into approval fatigue. Doing this properly needs a labelled corpus of
Hutch actions and a measured false-positive rate first. The safer half of the recommendation is already in place.

## 4. Make step and token budgets first-class, with no-progress detection

**Adopted.** `computer/limits.py` gives every run a 200-unit budget (observations and state-changing actions) and refuses
further state-changing actions after three consecutive actions that leave the framebuffer identical, while leaving
observation open because looking is how an agent recovers. A verified effect or any changed frame clears the count. Refusals
are `not_dispatched`, carry counters in every tool result, and never end a run: they hand the decision back to the model and
the person. Covered by `tests/test_computer_limits.py`, including a fake session that never changes the screen.

**Not adopted:** a token budget specific to computer use. Hutch already reserves and accounts model usage per run; adding a
second token ledger inside the tool would duplicate it. The action budget is the part the existing accounting cannot see.

**Honest limit:** the stall rule is frame-based, so it does not fire for a task that uses only semantic actions. Such a task
is bounded by the action budget alone. `docs/computer-use.md` says so.

## 5. Event triggers with signature verification and replay defence

**Not implemented.** This is a new internet-facing surface and deserves its own pass: a `trigger_events` table keyed by
`(source, event_id)`, HMAC over raw request bytes, a freshness window, and an asynchronous ack (S59, S6). Hutch's existing
scheduler already handles the *time* half of autonomous work correctly (croniter with IANA zones, catch-up after suspend,
per-bot single-instance serialization), and `computer/limits.py` now bounds what a triggered run may do. What is missing is
event identity, which cron has no equivalent of.

## 6. Remote-host execution

**Not implemented, deliberately last.** It is the largest new trust boundary in the list: pinned host keys, short-lived
credentials, a host allowlist and a fixed entrypoint (S51-S54). Nothing here weakens that decision, and the action budget and
fence work above apply unchanged if it is built later.

## What was explicitly *not* built

* No parallel agent system. Computer use remains one tool inside Hutch's existing bot, run, approval, budget, cancellation
  and audit machinery; the semantic path reuses the same `ControlLease`, `FrameStore` and receipt recording as pixels.
* No fake capability. A session without at-spi keeps working through pixels and records `semantics: unavailable` with the
  reason; `hutch computer doctor` reports which case applies, and the run panel tells the user.
* No claim of universal application support. The path is verified with one KDE application; GTK is expected to work and
  unverified, games and canvas-only applications have no tree.
