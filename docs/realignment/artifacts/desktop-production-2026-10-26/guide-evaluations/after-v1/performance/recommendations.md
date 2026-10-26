# Campaign Recommendations (draft — no changes made)

Source: `input.txt` (2 campaigns, one row each). No campaign settings, budgets, or bids were modified. Everything below is a proposal only.

## Metrics snapshot

| campaign | impressions | clicks | spend | conversions | revenue | daily_budget |
|---|---|---|---|---|---|---|
| Search | 10000 | 1000 | 300 | 20 | 1000 | 250 |
| Social | 20000 | 400 | 150 | 0 | 0 | 200 |

| campaign | CTR | CVR | CPA | ROAS | alert |
|---|---|---|---|---|---|
| Search | 0.1000 | 0.0200 | 15.0000 | 3.3333 | over_budget |
| Social | 0.0200 | 0.0000 | (undefined — 0 conversions) | 0.0000 | zero_conversions |

Derivations: CTR = clicks / impressions; CVR = conversions / clicks; CPA = spend / conversions; ROAS = revenue / spend. All ratios are rounded to 4 decimal places.

## What the data does and does not support

Observed:
- Search recorded spend of 300 against a `daily_budget` of 250, which is what triggers the `over_budget` flag.
- Social recorded zero conversions and zero revenue on 400 clicks.

Unknown / unverified:
- The period the `spend` column covers is not stated. If 300 is a multi-day total, spending above a **daily** budget of 250 may be entirely normal and the `over_budget` flag would be a false positive. This needs confirming from the account's date range before acting.
- ROAS is revenue/spend only. It is **not** profit or break-even: no COGS, fees, or other costs are in the file, so neither campaign's profitability is established. A ROAS of 3.33 does not prove Search is profitable.
- Social's zero conversions may reflect genuine non-performance, a measurement gap (broken conversion tracking), a very low volume, or a mismatch between click intent and landing page. The data cannot distinguish these.
- No historical baseline, seasonality, or benchmark CTR/CVR is provided, so "high"/"low" comparisons are not supported.
- Statistical confidence is thin: 20 conversions for Search and 0 for Social are both small samples.

## Recommendations (each requires explicit human approval before any spend changes)

1. **Search — verify the over_budget flag before doing anything.** Confirm the reporting period behind `spend`. If 300 is a single day's spend against a 250 daily cap, approve one of: (a) raise the daily budget to cover observed spend, (b) cap spend at 250 and accept reduced delivery, or (c) leave as is if the overspend is an intentional pacing choice. **Requires approval — no budget change proposed as automatic.**
2. **Search — hold spend steady pending margin data.** Before any scale-up, request COGS/margin and target CPA so ROAS 3.3333 can be converted into a profitability test. **Any increase in spend requires approval and margin data.**
3. **Social — investigate before reallocating.** Check conversion tracking/pixel health first, since a zero can be a measurement failure rather than poor performance. Only after that check should a decision be made. **Do not pause or reduce Social spend until the tracking check is done and a human approves.**
4. **Social — if tracking is confirmed healthy, propose (do not execute) a pausing or reallocation option** for human review, with the note that 400 clicks is a small sample and a single period is not enough to condemn the channel. **Approval required before any pause, budget cut, or fund move.**
5. **No cross-campaign budget shifts are recommended yet.** Shifting budget from Social to Search would require margin/breakeven data and a confirmed over_budget interpretation; neither exists in `input.txt`. **Any reallocation requires explicit approval.**

## Approval gate

Nothing in this document is a live change. Before executing any of items 1–5, a human owner must approve the specific action, its amount, and its effective date. Until then, campaigns remain unchanged.
