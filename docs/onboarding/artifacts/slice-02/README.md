# Slice 02 evidence pointer

This execution run stores the slice-02 evidence canonically under
[`docs/onboarding/evidence/slice-02/`](../../evidence/slice-02/):

- `chooser-*.png`, `handoff-*.png` - 57 live Chromium captures at 320x740,
  375x812, 768x1024 and 1440x1000, including forced colours, reduced motion,
  200 percent text scale, keyboard focus and OS light preference.
- `capture-results.json` - machine observations for every row.
- `validation.json` - independent opened-image verdicts (canonical copy here
  marked with `"canonical"`).

This pointer directory keeps the CP2 wording satisfied the same way slice 01
kept its artifacts pointer. The evidence was captured by
`tests/e2e/test_onboarding_chooser.py` against the real uvicorn app and real
routes; no static HTML fixture was reviewed.
