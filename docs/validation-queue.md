# Machine-wide validation queue (explicit opt-in)

Hutch can share the machine-wide admission and receipt queue used by the Varve
checkout. Adoption is **explicit**: the wrapper neither imports Varve code nor
assumes a sibling-checkout path.

```bash
export VARVE_QUEUE_CLI=/absolute/path/to/varve/scripts/quality/validation-queue.mjs

# Inspect the machine-wide holder/slots
uv run --frozen --no-sync python scripts/validation_queue.py status

# Run a focused gate through the queue
uv run --frozen --no-sync python scripts/validation_queue.py run \
  --label "pytest: focused" --class shared -- \
  uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_x.py
```

`--queue-cli <path>` overrides `VARVE_QUEUE_CLI` for one invocation. With
neither set, the wrapper exits 2 and explains the opt-in. There is no implicit
cross-repository default.

Queue state and receipts are machine-wide, but receipt identity includes the
repository common directory and HEAD, so Hutch never reuses a Varve receipt and
Varve never reuses a Hutch receipt. Receipts are local cache evidence only,
never CI evidence. Browser/Playwright runs stay with the existing Hutch
escalation policy; the queue does not change that boundary.

Tests: `tests/test_validation_queue.py`.
