# Recommendations (draft — approval required)

All figures below are derived only from `input.txt` (impressions, clicks, spend,
conversions, revenue, daily_budget) for the single period covered. They are not
margin, profit, or break-even evidence, and they do not cover attribution,
seasonality, or incrementality.

## Inputs used

| campaign | impressions | clicks | spend | conversions | revenue | daily_budget |
|---|---|---|---|---|---|---|
| Search | 10000 | 1000 | 300 | 20 | 1000 | 250 |
| Social | 20000 | 400 | 150 | 0 | 0 | 200 |

## Derived metrics (see metrics.csv)

| campaign | CTR | CVR | CPA | ROAS | alert |
|---|---|---|---|---|---|
| Search | 0.1 | 0.02 | 15 | 3.3333 | over_budget |
| Social | 0.02 | 0 | (undefined) | 0 | zero_conversions |

## Recommendations — none of these may be acted on without explicit human approval

1. **Search — do not change spend until approval.**
   Proposed (not executed): investigate why spend (300) exceeds the stated
   daily_budget (250) before any budget edit. Confirm whether the budget field
   is daily vs. period, and whether the period spans more than one day. A
   recorded overage in this single snapshot is a hypothesis about cause, not a
   proven overspend event.
   *Required approval:* human sign-off on the investigation scope and on any
   subsequent budget change.

2. **Social — do not change spend until approval.**
   Proposed (not executed): pause-or-fix decision only after confirming the
   zero-conversion result is not a tracking/attribution failure. CPA is
   undefined (zero conversions), so no cost-per-acquisition or break-even claim
   can be made from this data.
   *Required approval:* human sign-off before pausing, reducing, or reallocating
   any Social spend.

3. **No reallocation is recommended at this time.**
   Shifting budget from Social to Search is not justified by these numbers alone
   because ROAS here excludes margin, fees, and other full costs, and one period
   of data cannot establish a stable trend.

## Explicit approval gate

- No campaign has been changed, paused, or re-budgeted by this analysis.
- Every spend-affecting action listed above requires explicit approval from a
  human owner before it is taken.
- Until that approval is recorded, these items remain proposals only.
