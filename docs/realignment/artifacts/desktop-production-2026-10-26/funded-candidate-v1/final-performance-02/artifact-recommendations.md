# Recommendations (draft - all spend changes require human approval)

No campaign settings were changed. Every item below is a proposal only and must be
explicitly approved by a human operator before any spend, budget, or bid change is made.

## Inputs used
Source: `input.txt` (one row per campaign). Metrics in `metrics.csv`.

| campaign | impressions | clicks | spend | conversions | revenue | daily_budget |
|---|---|---|---|---|---|---|
| Search | 10000 | 1000 | 300 | 20 | 1000 | 250 |
| Social | 20000 | 400 | 150 | 0 | 0 | 200 |

## Search — alert: over_budget
Facts: CTR 0.1000, CVR 0.0200, CPA 15.0000, ROAS 3.3333. Recorded spend (300) exceeds
the listed daily_budget (250) for the period covered by the row.
- Proposal (needs approval): confirm the reporting period the 300 spend covers before any
  budget action; if it is a single day, treat the overrun as a pacing/overspend issue.
- Proposal (needs approval): if the overspend is real and intentional, raise the budget cap;
  if unintentional, reduce bids or add a daily cap. No change made pending approval.
- Caution: ROAS 3.3333 is revenue/spend only. It does not include margin, fees, or other
  costs, so it does not prove this campaign is profitable or at break-even.

## Social — alert: zero_conversions
Facts: CTR 0.0200, CVR 0.0000, CPA undefined (empty - no conversions), ROAS 0.0000.
Spend of 150 produced no conversions and no revenue in this data.
- Proposal (needs approval): before pausing or cutting spend, verify conversion tracking is
  firing for this campaign; zero conversions can be a measurement gap rather than a
  performance result.
- Proposal (needs approval): if tracking is confirmed and results stay flat over a defined
  evaluation window, shift budget away from Social. No change made pending approval.
- Caution: missing CPA is not evidence of savings or efficiency; it is simply undefined
  because the denominator (conversions) is zero.

## Scope and limits
- Values are computed directly from `input.txt`; no external or network data was used.
- Alert labels were assigned as instructed (Search = over_budget, Social = zero_conversions)
  and are flags for review, not verified conclusions.
- Unknowns: attribution window, currency, and the exact period each row covers.
