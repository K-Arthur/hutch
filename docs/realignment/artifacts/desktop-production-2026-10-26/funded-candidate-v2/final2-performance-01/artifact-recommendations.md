# Recommendations (draft — no changes made)

**Status: no campaigns were changed.** All items below are proposals that require explicit human approval before any spend or budget change is made.

## Observed facts (from input.txt)
- Search: impressions 10,000; clicks 1,000; spend 300; conversions 20; revenue 1,000; daily_budget 250.
- Social: impressions 20,000; clicks 400; spend 150; conversions 0; revenue 0; daily_budget 200.
- Derived: Search CTR 0.1, CVR 0.02, CPA 15, ROAS 3.3333. Social CTR 0.02, CVR 0, CPA undefined (no conversions), ROAS 0.
- Alert flags as requested: Search = over_budget; Social = zero_conversions.

## Unknowns / caveats
- Reporting period length is not given, so "over_budget" for Search (spend 300 vs daily_budget 250) is an instruction-based flag, not a verified budget breach.
- ROAS 3.3333 does not prove profit or break-even; no margin or full cost data was provided. Revenue-only ratios cannot establish profitability.
- Social CVR 0 is based on 400 clicks and a single reporting window; small-sample and attribution effects are unquantified.
- No ICP, audience-quality, or incrementality evidence was provided, so fit and causality are unverified.

## Proposals (each requires explicit approval before execution)

1. **Social — hold or pause pending review. Approval required before any spend change.**
   - Basis (fact): 0 conversions on 400 clicks, spend 150.
   - Hypothesis (unverified): spend is not converting in this window.
   - Proposed action if approved: pause or reduce Social spend, or keep running to gather more data.
   - Do not act without approval.

2. **Search — do not increase spend without approval.**
   - Basis (fact): ROAS 3.3333, CPA 15, spend 300 against daily_budget 250.
   - Hypothesis (unverified): this campaign is efficient and could absorb more budget. This cannot be confirmed without margin and full-cost data.
   - Proposed action if approved: review period length and budget rules first, then decide whether any budget change is warranted.
   - Do not act without approval.

3. **Data collection — no spend impact, approval still required to schedule.**
   - Add margin and full-cost fields so ROAS can be assessed against break-even.
   - Add conversion-value and period-length fields to disambiguate the over_budget flag.

## Explicit constraint
No campaign budgets, bids, statuses, or spend were modified. Any change to spend requires explicit approval from the responsible human owner.
