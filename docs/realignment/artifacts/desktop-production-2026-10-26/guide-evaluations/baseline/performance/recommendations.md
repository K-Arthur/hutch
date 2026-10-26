# Campaign Recommendations (Draft — No Changes Applied)

No campaigns, budgets, bids, or targeting settings have been modified. This document is
advisory only. **Every recommendation below requires explicit human approval before any
spend is changed.** Treat all figures as a draft pending review.

## Summary of current performance

| Campaign | Impressions | Clicks | Spend | Conversions | Revenue | CTR | CVR | CPA | ROAS | Alert |
|---|---|---|---|---|---|---|---|---|---|---|
| Search | 10,000 | 1,000 | 300 | 20 | 1,000 | 0.1000 | 0.0200 | 15.0000 | 3.3333 | over_budget |
| Social | 20,000 | 400 | 150 | 0 | 0 | 0.0200 | 0.0000 | — (undefined) | 0.0000 | zero_conversions |

Note: Social's CPA is undefined because there were zero conversions; it is intentionally
left blank in `metrics.csv` rather than reported as zero or infinity.

## Search — alert: over_budget

- Observed spend of 300 against a daily budget of 250, i.e. over budget for the period.
- Efficiency is healthy: CVR 0.0200 and ROAS 3.3333 (revenue 1,000 on 300 spend).
- **Recommendation (requires approval):** reconcile the over-delivery against the stated
  daily budget and confirm whether it is an accounting artifact (for example, a partial-day
  or multi-day capture) or genuine over-spend. Only after that confirmation, and only with
  explicit approval, consider raising the daily budget to a level the observed spend fits
  within, or capping delivery. Do not adjust the budget unilaterally.
- **Recommendation (requires approval):** because ROAS is comfortably above break-even,
  any increase in budget should be a deliberate, approved decision with a defined cap and a
  review date, not an automatic response to strong ROAS.

## Social — alert: zero_conversions

- Strong reach (20,000 impressions) but weak engagement (CTR 0.0200 versus 0.1000 for
  Search) and no conversions at all, so 150 of spend returned 0 revenue (ROAS 0.0000).
- **Recommendation (requires approval):** pause or reduce Social spend only after approval,
  and ideally only once tracking has been verified — zero conversions may reflect a
  measurement gap (missing or broken conversion event) rather than a true performance result.
- **Recommendation (requires approval):** before any budget change, verify conversion
  tracking and landing-page flow, then review creative and targeting. If tracking is sound
  and performance persists, an approved, time-boxed budget reduction is the preferred
  first step over an immediate full pause.

## Guardrails for all proposed changes

1. No spend changes take effect without explicit approval from the campaign owner.
2. Each approved change should specify the campaign, the exact new budget, the effective
   date, and the owner who approved it.
3. Changes should be made one campaign at a time so impact can be attributed and measured.
4. Re-measure at the agreed review date and revert any change that underperforms the plan.
5. This document records recommendations only; the campaign state remains unchanged.
