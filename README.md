# Backlog Bounty — August 2026

Daily leaderboard for the Launch team's August 2026 aging-case spiff.

**→ [View the live dashboard](https://brianmarzo.github.io/Backlog-Bounty/)**

## The rules

| Cohort of the case | Payout per August launch |
|---|---|
| March 2026 or earlier | **$40** |
| April or May 2026 | **$20** |
| June 2026 or later | $0 — not backlog |

Plus a **$100 pod prize** for the highest activation rate, and a hard deadline: any case
in onboarding 3+ months that hasn't launched by **August 31** gets churned, not DQ'd.
So every qualifying open case is simultaneously a payout and a churn liability.

## What's in here

| File | What it does |
|---|---|
| `build_dashboard.py` | Runs the queries, builds the HTML. Re-run any time to refresh. |
| `queries/bounty_cases.sql` | August launches, with cohort and bounty value per case. |
| `queries/open_backlog.sql` | Aged cases still open — the remaining opportunity and churn risk. |
| `queries/cohort_activation.sql` | Activation rate by assignment-month cohort, per rep. |
| `queries/cohort_case_detail.sql` | Every non-launched case behind each matrix cell — the drill-down. |

## Refreshing it

```bash
python3 build_dashboard.py
```

Pulls from Snowflake via the `snow` CLI, writes `data/*.json`, then renders
`Backlog_Bounty_<date>.html`. To rebuild the page from the last pull without
re-querying, add `--no-refresh`.

## Two data notes worth knowing

**Cohort date is `COALESCE(Onboarding_Start_Date__c, CreatedDate)`.** Using the onboarding
start date alone drops 59 open aged cases where that field is blank, which undercounts the
backlog by ~10% (541 instead of 600). The fallback keeps them in scope.

**Activation = launched ÷ every case assigned that month.** Cases still open, canceled, or
DQ'd all stay in the denominator. This is deliberately not closed-case activation, so recent
cohorts read low by design while they're still inside a normal launch cycle.

## Scope

The seven participating frontline pods: Adam Hubbell, Andrea Novais, Edison Blanco,
Juan Sanabria, Diego Orjuela, Amada Romero, Santiago Romero.

## ⚠️ The HTML is no longer aggregate-only

As of the drill-down build (2026-08-10), `index.html` embeds **~3,100 customer account
names, case numbers, and statuses** so the matrix cells can be opened. Raw query output in
`data/` is still gitignored, but the HTML itself now carries the same customer data.

**This repo publishes `index.html` to GitHub Pages at a public URL.** Pushing the
drill-down build puts those restaurant names on the open internet. Decide deliberately
before `git push`: either make the repo private, or strip account names from the payload
(`case_detail_payload()` in `build_dashboard.py` — drop the `"a"` key) and publish
case numbers only.
