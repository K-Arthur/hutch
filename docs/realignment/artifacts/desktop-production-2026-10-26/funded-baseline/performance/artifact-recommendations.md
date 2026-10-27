# Recommendations (draft — no changes made)

All figures are derived from `input.txt`. No campaign was modified.

## Search
- Observed: impressions 10,000; clicks 1,000; spend 300; conversions 20; revenue 1,000; daily_budget 250.
- Calculated: CTR 0.1 (10%), CVR 0.02 (2%), CPA 15, ROAS 3.3333.
- Alert: **over_budget** — spend (300) exceeds the stated daily_budget (250).
- Recommendation: review the budget cap and the delivery that caused spend to exceed the daily_budget. If an increase in daily_budget is desired, **obtain explicit human approval before changing spend**. Do not treat ROAS 3.3333 as proof of profitability — margin and full costs are unknown.

## Social
- Observed: impressions 20,000; clicks 400; spend 150; conversions 0; revenue 0; daily_budget 200.
- Calculated: CTR 0.02 (2%), CVR 0 (0%), CPA undefined (no conversions — left empty), ROAS 0.
- Alert: **zero_conversions** — 150 spent with no conversions and no revenue.
- Recommendation: investigate tracking, targeting and creative before any budget action. Any reduction, pause or reallocation of spend **requires explicit human approval first**. CPA cannot be assessed because there are no conversions.

## Unknowns / assumptions
- CTR and CVR are computed as clicks/impressions and conversions/clicks respectively.
- Attribution windows, margin, and full cost structure are not provided; ROAS is reported as given and is not evidence of profit.
- "over_budget" is inferred by comparing spend to the supplied daily_budget for the period; the period definition is unknown.

## Required gate
No spend change is proposed here. Any change to budgets, bids, or spend allocation must be approved by a human owner before execution.
