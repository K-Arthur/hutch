# FRONTEND-GATE.md — Pre-Implementation Gate Record (Run 4 / Pipeline Run 7)

Date: `2026-10-29`
Pipeline: `.pipeline/brand/2026-10/`
Active Slice: **Slice 7A — Licence, Font & Brand Docs Reconciliation**

---

## 1. Preconditions Verified Before Writing Outside `.pipeline/brand/**`

| Gate Item | Status | Evidence |
| :--- | :--- | :--- |
| **1. Evidence base signed off (Run 1)** | **PASS** | `DECISION.md` `D09` (`2026-10-28`). |
| **2. Direction & IP pre-screen accepted (Run 2)** | **PASS** | Name `"Hutch"` retained (`D10`/`D38`), tagline retained (`D11`), neutral ramp `website/tokens.json` (`D12`), written risk ownership (`D20`/`D23`/`D28`/`D38`). |
| **3. Mark, wordmark, colour & guidelines approved (Runs 3–6)** | **PASS** | Wordmark lowercase `"hutch."` in Bricolage Grotesque 800 (`D42`), Colour System (`D43`/`D46`), Mark **Direction B — "Visor Hutch"** selected (`D54`), 78-file production & press-kit package built (`D55`), pre-screen updated (`D56`). |
| **4. Explicit dated human authorisation for repository integration (`B6`)** | **PASS (`D57`, `2026-10-29`)** | Maintainer instruction on `2026-10-29` ("proceed with the next slice/phase of work we have") following the First Response Contract naming **Slice 7A** as the recommended slice. |
| **5. Concurrency & worktree collision check** | **PASS** | Checked `git status --short`: `THIRD_PARTY_NOTICES.md`, `website/THIRD_PARTY_NOTICES.txt`, `src/hutch/server/static/THIRD_PARTY_NOTICES.txt`, `docs/brand-assets.md`, `docs/design-system.md`, `website/assets/fonts/*`, and `src/hutch/server/static/fonts/*` have **zero** uncommitted changes from other sessions. |
| **6. 3-File / 1-Seam boundary** | **PASS** | Edited prose/source files outside `.pipeline/brand/**`: (1) `THIRD_PARTY_NOTICES.md` (+ its two exact mirrors `website/THIRD_PARTY_NOTICES.txt` and `src/hutch/server/static/THIRD_PARTY_NOTICES.txt` per `scripts/stamp_site_assets.mjs:22-24`), (2) `docs/brand-assets.md`, (3) `docs/design-system.md`; plus one cross-cutting seam: staging the identical `bricolage-grotesque-latin-800.woff2` + `OFL-bricolage-grotesque.txt` pair into `website/assets/fonts/` and `src/hutch/server/static/fonts/`. |

---

## 2. Frontend & Hygiene Constraints Enforced

1. **No generated CSS hand-edits:** `src/hutch/server/static/ui.css`, `model-switcher.css`, `website/app.css`, and `website/styles.min.css` are not touched in Slice 7A.
2. **No dirty-file interference:** Do not run `scripts/stamp_site_assets.mjs` or `npm run build:css` in Slice 7A because `app/src/input.css` and `app/src/model-switcher.css` have uncommitted changes in the working tree from another session. Instead, sync `website/THIRD_PARTY_NOTICES.txt` and `src/hutch/server/static/THIRD_PARTY_NOTICES.txt` directly from `THIRD_PARTY_NOTICES.md` (`cmp` byte-identical check).
3. **File-size ceiling (`<= 400` lines):** Every new or modified file stays well below the 400-line ceiling enforced by `scripts/audit_context_hygiene.py`.
4. **No emoji:** Verified via `uv run --frozen --no-sync python scripts/audit_emoji.py`.
5. **Legal language discipline:** All brand documentation preserves explicit non-clearance disclaimers ("not a legal opinion or a grant of trademark rights"; "do not present the Hutch logomark or wordmark as a registered trademark").
