#!/usr/bin/env python3
"""Backlog Bounty (August 2026) dashboard builder — Owner-branded.

Runs the three Snowflake queries in ./queries, then renders a gamified
single-page scoreboard covering every Launch manager pod.

Usage:  python3 build_dashboard.py
"""

import json
import sys
import subprocess
import datetime as dt
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
QUERIES = ROOT / "queries"

QUERY_NAMES = ("bounty_cases", "open_backlog", "cohort_activation")

BOUNTY_END = dt.date(2026, 8, 31)

# Cohort columns shown in the activation matrix.
MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"]
MONTH_LABEL = {"2026-01": "Jan", "2026-02": "Feb", "2026-03": "Mar", "2026-04": "Apr",
               "2026-05": "May", "2026-06": "Jun", "2026-07": "Jul"}
# Months that carry a bounty if launched in August.
TIER_40 = ["pre-2026", "2026-01", "2026-02", "2026-03"]
TIER_20 = ["2026-04", "2026-05"]
# Cohorts used for the *activation* read on bounty months. Deliberately excludes the
# pre-2026 bucket — that's a years-deep catch-all that swamps the denominator and makes
# the rate meaningless. Jan–May 2026 are mature enough to read as close to final.
BOUNTY_ACT_MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]

# Participating pods only, mapped to the director they roll up to.
# Sasan Mahinpourian's POS Launch org is NOT in the spiff and is excluded entirely.
# Directors (Brian, Dave, Andres) don't get their own pod row — their frontline
# managers' pods are the unit of competition; the director row is the rollup.
POD_DIRECTOR = {
    "Adam Hubbell":    "Brian Marzo",
    "Andrea Novais":   "Brian Marzo",
    "Edison Blanco":   "Dave Candia",
    "Juan Sanabria":   "Dave Candia",
    "Diego Orjuela":   "Andres Bonilla",
    "Amada Romero":    "Andres Bonilla",
    "Santiago Romero": "Andres Bonilla",
}
BRIAN_PODS = [p for p, d in POD_DIRECTOR.items() if d == "Brian Marzo"]


def run_queries():
    DATA.mkdir(exist_ok=True)
    for name in QUERY_NAMES:
        out = subprocess.run(
            ["snow", "sql", "-f", str(QUERIES / f"{name}.sql"), "--format", "json"],
            capture_output=True, text=True,
        )
        if out.returncode != 0:
            raise SystemExit(f"Query {name} failed:\n{out.stderr}")
        (DATA / f"{name}.json").write_text(out.stdout)


# Snowflake's JSON output serializes numeric columns as strings.
INT_COLS = ("BOUNTY_USD", "BOUNTY_IF_LAUNCHED", "ASSIGNED", "LAUNCHED", "STILL_OPEN",
            "CANCELED", "CLOSED_OTHER", "DAYS_IN_ONBOARDING", "DAYS_OPEN")
FLOAT_COLS = ("ACTIVATION_PCT", "GP_SCORE")


def load(name):
    rows = json.loads((DATA / f"{name}.json").read_text())
    for r in rows:
        for k in INT_COLS:
            if r.get(k) is not None:
                r[k] = int(float(r[k]))
        for k in FLOAT_COLS:
            if r.get(k) is not None:
                r[k] = float(r[k])
        if not r.get("MANAGER"):
            r["MANAGER"] = "Unassigned pod"
    return rows


def build_model():
    cases = load("bounty_cases")
    backlog = load("open_backlog")
    cohorts = load("cohort_activation")

    reps = {}

    def slot(name, manager, title=None):
        if name not in reps:
            reps[name] = {
                "rep": name, "manager": manager, "title": title or "",
                "gold": 0, "silver": 0, "earned": 0, "aug_launches": 0,
                "open_gold": 0, "open_silver": 0, "available": 0, "churn_risk": 0,
                "cohort": {}, "assigned_2026": 0, "launched_2026": 0,
                "open_by_month": defaultdict(int),
            }
        return reps[name]

    for c in cases:
        r = slot(c["REP"], c["MANAGER"], c["TITLE"])
        r["aug_launches"] += 1
        b = c["BOUNTY_USD"]
        if b == 40:
            r["gold"] += 1
        elif b == 20:
            r["silver"] += 1
        r["earned"] += b

    for c in backlog:
        r = slot(c["REP"], c["MANAGER"])
        b = c["BOUNTY_IF_LAUNCHED"]
        if b == 40:
            r["open_gold"] += 1
        elif b == 20:
            r["open_silver"] += 1
        r["available"] += b
        r["churn_risk"] += 1
        month = c["COHORT_MONTH"] if c["COHORT_MONTH"] >= "2026-01" else "pre-2026"
        r["open_by_month"][month] += 1

    for c in cohorts:
        r = slot(c["REP"], c["MANAGER"], c["TITLE"])
        r["cohort"][c["COHORT_MONTH"]] = c
        if c["COHORT_MONTH"] != "pre-2026":
            r["assigned_2026"] += c["ASSIGNED"]
            r["launched_2026"] += c["LAUNCHED"]

    return list(reps.values())


def pod_rollup(reps):
    pods = defaultdict(lambda: {
        "earned": 0, "available": 0, "gold": 0, "silver": 0, "churn_risk": 0,
        "open_gold": 0, "open_silver": 0, "aug_launches": 0,
        "assigned_2026": 0, "launched_2026": 0, "reps": [],
        "cohort": defaultdict(lambda: {"ASSIGNED": 0, "LAUNCHED": 0}),
    })
    for r in reps:
        p = pods[r["manager"]]
        for k in ("earned", "available", "gold", "silver", "churn_risk",
                  "open_gold", "open_silver", "aug_launches",
                  "assigned_2026", "launched_2026"):
            p[k] += r[k]
        p["reps"].append(r)
        for m, c in r["cohort"].items():
            p["cohort"][m]["ASSIGNED"] += c["ASSIGNED"]
            p["cohort"][m]["LAUNCHED"] += c["LAUNCHED"]
    for p in pods.values():
        p["activation"] = pct(p["launched_2026"], p["assigned_2026"])
        p["reps"].sort(key=lambda r: (-r["earned"], -r["available"], r["rep"]))
    return pods


def pct(num, den):
    return round(100 * num / den, 1) if den else None


def money(n):
    return f"${n:,.0f}"


def act_class(v):
    if v is None:
        return ""
    return "good" if v >= 85 else ("ok" if v >= 75 else ("warn" if v >= 60 else "bad"))


def slug(s):
    return "".join(ch if ch.isalnum() else "-" for ch in s).lower()


# ---------------------------------------------------------------- sections

def pod_standings(pods, order):
    rows = []
    for i, mgr in enumerate(order):
        p = pods[mgr]
        pool = p["earned"] + p["available"]
        claimed = pct(p["earned"], pool) or 0
        star = " \u2b50" if mgr in BRIAN_PODS else ""
        rows.append(f"""<tr>
  <td class="rank">{i+1}</td>
  <td class="name">{mgr}{star}<span class="sub">{len(p['reps'])} reps · {p['aug_launches']} Aug launches</span></td>
  <td class="num money-won">{money(p['earned'])}</td>
  <td class="num money-open">{money(p['available'])}</td>
  <td class="num"><span class="chip chip-gold">{p['open_gold']}</span> <span class="chip chip-blue">{p['open_silver']}</span></td>
  <td class="num danger">{p['churn_risk']}</td>
  <td class="num {act_class(p['activation'])}">{fmt_pct(p['activation'])}</td>
  <td class="barcell"><div class="minibar"><div style="width:{claimed:.1f}%"></div></div><span class="sub">{claimed:.0f}% claimed</span></td>
</tr>""")
    return f"""<table class="tbl">
<thead><tr><th>#</th><th>Pod</th><th class="num">Claimed</th><th class="num">On the table</th>
<th class="num">Open $40 / $20</th><th class="num">Churn risk</th>
<th class="num">Activation<br><span class="sub">2026 cohorts</span></th><th>Progress</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>"""


def fmt_pct(v):
    return f"{v:.0f}%" if v is not None else "—"


def target_list(reps, limit=25):
    ranked = sorted([r for r in reps if r["available"] > 0],
                    key=lambda r: (-r["open_gold"], -r["available"]))[:limit]
    rows = []
    for r in ranked:
        act = r["cohort"]
        a = sum(act[m]["ASSIGNED"] for m in BOUNTY_ACT_MONTHS if m in act)
        l = sum(act[m]["LAUNCHED"] for m in BOUNTY_ACT_MONTHS if m in act)
        ba = pct(l, a)
        # Below ~10 cases the rate is noise — show the raw split, not a headline %.
        # These reps are typically holding pre-2026 inventory with almost no 2026 assignments.
        if a < 10:
            cell = f'<td class="num muted">n/a<span class="sub">{l}/{a} assigned</span></td>'
        else:
            cell = f'<td class="num {act_class(ba)}">{fmt_pct(ba)}<span class="sub">{l}/{a}</span></td>'
        rows.append(f"""<tr data-pod="{slug(r['manager'])}">
  <td class="name">{r['rep']}<span class="sub">{r['manager']}</span></td>
  <td class="num"><span class="chip chip-gold">{r['open_gold']}</span></td>
  <td class="num"><span class="chip chip-blue">{r['open_silver']}</span></td>
  <td class="num money-open big">{money(r['available'])}</td>
  <td class="num danger">{r['churn_risk']}</td>
  {cell}
  <td class="num money-won">{money(r['earned'])}</td>
</tr>""")
    return f"""<table class="tbl">
<thead><tr><th>Rep</th><th class="num">Open $40<br><span class="sub">Mar &amp; older</span></th>
<th class="num">Open $20<br><span class="sub">Apr–May</span></th><th class="num">$ on the table</th>
<th class="num">Churn risk</th><th class="num">Activation<br><span class="sub">Jan–May cohorts</span></th>
<th class="num">Claimed</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>"""


def leaderboard(reps):
    ranked = sorted(reps, key=lambda r: (-r["earned"], -r["gold"], -r["available"], r["rep"]))
    ranked = [r for r in ranked if r["earned"] or r["available"] or r["aug_launches"]]
    rows = []
    for i, r in enumerate(ranked):
        medal = {0: "\U0001f947", 1: "\U0001f948", 2: "\U0001f949"}.get(i, "")
        rows.append(f"""<tr data-pod="{slug(r['manager'])}">
  <td class="rank">{medal or i+1}</td>
  <td class="name">{r['rep']}<span class="sub">{r['manager']}</span></td>
  <td class="num">{r['aug_launches']}</td>
  <td class="num"><span class="chip chip-gold">{r['gold'] or '·'}</span></td>
  <td class="num"><span class="chip chip-blue">{r['silver'] or '·'}</span></td>
  <td class="num money-won big">{money(r['earned'])}</td>
  <td class="num money-open">{money(r['available'])}</td>
</tr>""")
    return f"""<table class="tbl">
<thead><tr><th>#</th><th>Rep</th><th class="num">Aug launches</th>
<th class="num">$40 cases</th><th class="num">$20 cases</th>
<th class="num">Earned</th><th class="num">Still available</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>"""


def activation_matrix(reps):
    ranked = sorted(reps, key=lambda r: (r["manager"], -r["assigned_2026"]))
    ranked = [r for r in ranked if r["assigned_2026"] >= 5]
    rows = []
    for r in ranked:
        cells = []
        for m in MONTHS:
            c = r["cohort"].get(m)
            if not c or not c["ASSIGNED"]:
                cells.append('<td class="num muted">·</td>')
                continue
            v = c["ACTIVATION_PCT"]
            tier = "t40" if m in TIER_40 else ("t20" if m in TIER_20 else "")
            cells.append(
                f'<td class="num cell {act_class(v)} {tier}" '
                f'title="{c["LAUNCHED"]} launched / {c["ASSIGNED"]} assigned · '
                f'{c["STILL_OPEN"]} open · {c["CANCELED"]} canceled">'
                f'{v:.0f}%<span class="sub">{c["LAUNCHED"]}/{c["ASSIGNED"]}</span></td>')
        tot = pct(r["launched_2026"], r["assigned_2026"])
        rows.append(f"""<tr data-pod="{slug(r['manager'])}">
  <td class="name">{r['rep']}<span class="sub">{r['manager']}</span></td>
  {''.join(cells)}
  <td class="num tot {act_class(tot)}">{fmt_pct(tot)}<span class="sub">{r['launched_2026']}/{r['assigned_2026']}</span></td>
</tr>""")
    heads = "".join(
        f'<th class="num {"t40" if m in TIER_40 else ("t20" if m in TIER_20 else "")}">{MONTH_LABEL[m]}</th>'
        for m in MONTHS)
    return f"""<table class="tbl matrix">
<thead><tr><th>Rep</th>{heads}<th class="num">2026 total</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>"""


def pod_tabs(order):
    btns = ['<button class="tab active" data-target="all">All pods</button>']
    for m in order:
        star = " \u2b50" if m in BRIAN_PODS else ""
        btns.append(f'<button class="tab" data-target="{slug(m)}">{m}{star}</button>')
    return f'<div class="tabs">{"".join(btns)}</div>'


# ---------------------------------------------------------------- render

def render(reps, generated):
    days_left = (BOUNTY_END - generated).days
    reps = [r for r in reps if r["manager"] in POD_DIRECTOR]
    pods = pod_rollup(reps)

    live = list(pods.keys())
    order = sorted(live, key=lambda m: -(pods[m]["earned"] + pods[m]["available"]))
    scoped = reps

    t_earned = sum(r["earned"] for r in scoped)
    t_avail = sum(r["available"] for r in scoped)
    t_gold = sum(r["gold"] for r in scoped)
    t_silver = sum(r["silver"] for r in scoped)
    t_risk = sum(r["churn_risk"] for r in scoped)
    open_gold = sum(r["open_gold"] for r in scoped)
    open_silver = sum(r["open_silver"] for r in scoped)
    claimed_pct = pct(t_earned, t_earned + t_avail) or 0

    b_assigned = sum(p["assigned_2026"] for m, p in pods.items() if m in live)
    b_launched = sum(p["launched_2026"] for m, p in pods.items() if m in live)

    # Activation on the bounty months only — this is the number the 85% goal is about.
    ba_assigned = sum(c["ASSIGNED"] for r in scoped for m, c in r["cohort"].items()
                      if m in BOUNTY_ACT_MONTHS)
    ba_launched = sum(c["LAUNCHED"] for r in scoped for m, c in r["cohort"].items()
                      if m in BOUNTY_ACT_MONTHS)
    bounty_act = pct(ba_launched, ba_assigned)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Backlog Bounty · August 2026 · Owner</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@350;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{
  --owner-green:#088924; --bright-green:#0CB230; --deep-green:#115C1E; --darkest-green:#094413;
  --near-black:#2C2C2C; --white:#FFFFFF; --warm-white:#FBF8F5; --warm-cream:#F9F3ED;
  --warm-beige:#F6EEE5; --warm-gray:#DDD6CE; --warm-gray-dark:#C5BEB7;
  --sky-blue:#56AEDD; --deep-blue:#034F81; --violet:#746CCF; --gold:#DDAD6B; --deep-gold:#C58A3A;
  --alert:#B3402F;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--warm-cream); color:var(--near-black);
  font-family:'STK Bureau Sans',Inter,system-ui,sans-serif; font-size:18px; line-height:1.6;
  letter-spacing:-0.36px; -webkit-font-smoothing:antialiased; }}
.wrap {{ max-width:1360px; margin:0 auto; padding:0 32px 80px; }}

/* ---- hero ---- */
.hero {{ background:linear-gradient(180deg,#0CB230 0%,#094413 100%);
  border-radius:0 0 30px 30px; color:var(--white); padding:38px 32px 44px; margin-bottom:34px;
  position:relative; overflow:hidden; }}
.hero::after {{ content:""; position:absolute; right:-120px; top:-160px; width:520px; height:520px;
  border-radius:50%; background:radial-gradient(circle,rgba(255,255,255,.16),transparent 62%); }}
.hero-in {{ max-width:1360px; margin:0 auto; display:flex; justify-content:space-between;
  align-items:flex-end; gap:28px; flex-wrap:wrap; position:relative; z-index:1; }}
.brandmark {{ display:flex; align-items:center; gap:11px; font-weight:700; font-size:19px;
  letter-spacing:-0.4px; opacity:.95; margin-bottom:18px; }}
.brandmark .star {{ width:26px; height:26px; background:var(--white); color:var(--owner-green);
  border-radius:8px; display:grid; place-items:center; font-size:16px; }}
h1 {{ font-size:58px; font-weight:700; letter-spacing:-1.3px; line-height:1.05; margin:0; }}
.hero .lede {{ font-size:19px; opacity:.9; margin-top:12px; max-width:640px; font-weight:350; }}
.counter {{ text-align:right; background:rgba(255,255,255,.13); border:1px solid rgba(255,255,255,.24);
  border-radius:24px; padding:20px 30px; backdrop-filter:blur(8px); }}
.counter .n {{ font-size:64px; font-weight:700; line-height:1; letter-spacing:-2px; }}
.counter .l {{ font-size:14px; opacity:.88; margin-top:4px; }}

/* ---- type ---- */
h2 {{ font-size:32px; font-weight:700; letter-spacing:-0.64px; line-height:1.2; margin:52px 0 6px; }}
h2 .em {{ color:var(--owner-green); }}
.deck {{ font-size:16px; color:#6b6660; font-weight:350; margin:0 0 20px; max-width:820px; }}
.sub {{ display:block; font-size:12.5px; color:#8a837b; font-weight:400; letter-spacing:0; margin-top:2px; }}

/* ---- kpis ---- */
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:16px; }}
.kpi {{ background:var(--warm-white); border:1px solid var(--warm-gray); border-radius:24px; padding:22px 24px; }}
.kpi .v {{ font-size:40px; font-weight:700; letter-spacing:-1.4px; line-height:1; }}
.kpi .l {{ font-size:13px; color:#6b6660; margin-top:8px; letter-spacing:0; }}
.kpi.green {{ background:linear-gradient(165deg,#088924,#094413); border-color:transparent; color:var(--white); }}
.kpi.green .l {{ color:rgba(255,255,255,.85); }}
.kpi.goldk .v {{ color:var(--deep-gold); }}
.kpi.bluek .v {{ color:var(--deep-blue); }}
.kpi.alertk .v {{ color:var(--alert); }}

.bigbar {{ height:16px; background:var(--warm-beige); border:1px solid var(--warm-gray);
  border-radius:99px; overflow:hidden; margin-top:22px; }}
.bigbar > div {{ height:100%; background:linear-gradient(90deg,#0CB230,#088924); border-radius:99px; }}

/* ---- tables ---- */
.card {{ background:var(--warm-white); border:1px solid var(--warm-gray); border-radius:24px;
  padding:8px 24px 14px; overflow-x:auto; }}
table.tbl {{ width:100%; border-collapse:collapse; font-size:15px; letter-spacing:-0.2px; }}
table.tbl th {{ text-align:left; font-size:12px; font-weight:600; color:#6b6660; letter-spacing:0;
  padding:16px 12px 10px; border-bottom:2px solid var(--warm-gray); vertical-align:bottom; }}
table.tbl th.num {{ text-align:right; }}
table.tbl td {{ padding:13px 12px; border-bottom:1px solid var(--warm-beige); vertical-align:middle; }}
table.tbl tbody tr:hover {{ background:var(--warm-beige); }}
table.tbl tbody tr:last-child td {{ border-bottom:none; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.rank {{ color:#a09890; width:48px; font-size:17px; }}
.name {{ font-weight:600; }}
.name .sub {{ font-weight:400; }}
.dir {{ color:#8a837b; font-size:13.5px; }}
.big {{ font-size:17px; }}
.money-won {{ color:var(--owner-green); font-weight:700; }}
.money-open {{ color:var(--deep-gold); font-weight:600; }}
.danger {{ color:var(--alert); font-weight:600; }}
.good {{ color:var(--owner-green); font-weight:600; }}
.ok {{ color:var(--deep-green); }}
.warn {{ color:var(--deep-gold); font-weight:600; }}
.bad {{ color:var(--alert); font-weight:700; }}
.muted {{ color:var(--warm-gray-dark); }}
.chip {{ display:inline-block; min-width:30px; padding:3px 9px; border-radius:99px;
  font-size:13px; font-weight:700; letter-spacing:0; }}
.chip-gold {{ background:var(--gold); color:#4a3410; }}
.chip-blue {{ background:var(--sky-blue); color:#04304f; }}
.minibar {{ width:110px; height:9px; background:var(--warm-beige); border-radius:99px;
  overflow:hidden; display:inline-block; vertical-align:middle; }}
.minibar > div {{ height:100%; background:var(--owner-green); border-radius:99px; }}
.barcell .sub {{ display:inline-block; margin-left:9px; }}

/* ---- matrix ---- */
table.matrix td.cell {{ font-weight:600; }}
table.matrix th.t40, table.matrix td.t40 {{ background:rgba(221,173,107,.16); }}
table.matrix th.t20, table.matrix td.t20 {{ background:rgba(86,174,221,.14); }}
table.matrix td.tot {{ border-left:2px solid var(--warm-gray); font-weight:700; }}

/* ---- tabs ---- */
.tabs {{ display:flex; flex-wrap:wrap; gap:8px; margin:0 0 18px; }}
.tab {{ font-family:inherit; font-size:14px; font-weight:500; letter-spacing:-0.2px;
  background:var(--warm-beige); color:var(--near-black); border:1px solid var(--warm-gray);
  border-radius:99px; padding:8px 18px; cursor:pointer; transition:all .15s; }}
.tab:hover {{ background:var(--warm-gray); }}
.tab.active {{ background:var(--owner-green); border-color:var(--owner-green); color:var(--white); }}

/* ---- legend / notes ---- */
.note {{ background:var(--warm-beige); border-left:4px solid var(--owner-green);
  border-radius:0 20px 20px 0; padding:18px 24px; font-size:15px; color:#5d5852;
  margin-top:18px; letter-spacing:-0.2px; }}
.note b {{ color:var(--near-black); }}
.legend {{ display:flex; gap:22px; flex-wrap:wrap; font-size:13.5px; color:#6b6660; margin:14px 0 0; }}
.legend i {{ width:14px; height:14px; border-radius:5px; display:inline-block;
  vertical-align:-2px; margin-right:7px; }}
footer {{ margin-top:56px; padding-top:22px; border-top:1px solid var(--warm-gray);
  color:#8a837b; font-size:13.5px; line-height:1.85; letter-spacing:-0.2px; }}
footer b {{ color:#5d5852; }}
code {{ background:var(--warm-beige); padding:2px 7px; border-radius:6px; font-size:12.5px; }}
</style></head><body>

<div class="hero"><div class="hero-in">
  <div>
    <div class="brandmark"><span class="star">&#9733;</span> Owner · Launch</div>
    <h1>Backlog Bounty</h1>
    <div class="lede">Every aged case launched in August pays out — and every one left open
      on the 31st gets churned. Here's where the money and the risk are sitting.</div>
  </div>
  <div class="counter"><div class="n">{days_left}</div><div class="l">days left · closes Aug 31</div></div>
</div></div>

<div class="wrap">

<div class="kpis">
  <div class="kpi green"><div class="v">{money(t_earned)}</div><div class="l">Claimed so far</div></div>
  <div class="kpi goldk"><div class="v">{money(t_avail)}</div><div class="l">Still on the table</div></div>
  <div class="kpi"><div class="v">{t_gold} <span style="font-size:20px;color:#8a837b">/ {t_silver}</span></div>
    <div class="l">$40 / $20 cases launched</div></div>
  <div class="kpi alertk"><div class="v">{open_gold + open_silver}</div>
    <div class="l">Qualifying cases still open — <b>all {t_risk} face forced churn Aug 31</b><br>
      {open_gold} at $40 · {open_silver} at $20</div></div>
  <div class="kpi bluek"><div class="v">{fmt_pct(bounty_act)}</div>
    <div class="l">Activation on Jan–May cohorts<br>vs. the 85% goal</div></div>
</div>
<div class="bigbar"><div style="width:{claimed_pct:.1f}%"></div></div>
<div class="deck" style="margin-top:9px">{claimed_pct:.1f}% of the reachable pool claimed —
  {money(t_earned)} of {money(t_earned + t_avail)}. Org activation on 2026 cohorts is
  <b>{fmt_pct(pct(b_launched, b_assigned))}</b> ({b_launched:,} launched of {b_assigned:,} assigned).</div>

<h2>Pod <span class="em">standings</span></h2>
<p class="deck">Each frontline manager pod, ranked by total bounty in reach.</p>
<div class="card">{pod_standings(pods, order)}</div>

<h2>Who needs the <span class="em">most help</span></h2>
<p class="deck">Ranked by the number of $40 cases still sitting open — these reps are carrying the
  most aged inventory, so they're where a manager hour buys the most launches. Every case here is
  simultaneously a payout and a churn liability.</p>
{pod_tabs(order)}
<div class="card">{target_list(scoped)}</div>

<h2>Rep <span class="em">leaderboard</span></h2>
<p class="deck">August launches and bounty earned to date.</p>
{pod_tabs(order)}
<div class="card">{leaderboard(scoped)}</div>

<h2>Activation rate by <span class="em">assignment month</span></h2>
<p class="deck">Of the cases assigned to a rep in a given month, how many have launched as of today.
  Cases still open, canceled, or DQ'd all stay in the denominator. Shaded columns carry a bounty:
  <b>gold = $40</b> (Mar &amp; older), <b>blue = $20</b> (Apr–May). Hover a cell for the split.</p>
{pod_tabs(order)}
<div class="card">{activation_matrix(scoped)}</div>
<div class="legend">
  <span><i style="background:rgba(221,173,107,.55)"></i>$40 bounty cohort</span>
  <span><i style="background:rgba(86,174,221,.5)"></i>$20 bounty cohort</span>
  <span><i style="background:#088924"></i>85%+ </span>
  <span><i style="background:#115C1E"></i>75–85%</span>
  <span><i style="background:#C58A3A"></i>60–75%</span>
  <span><i style="background:#B3402F"></i>under 60%</span>
</div>
<div class="note">Jun and Jul cohorts read low on purpose — those cases are still inside a normal
  launch cycle. Read <b>Jan through May</b> as close to final: anything short of ~85% there is
  backlog that never converted, and the open remainder is exactly what this spiff is paying to clear.</div>

<footer>
  Generated {generated:%B %-d, %Y} from <b>PC_FIVETRAN_DB.SALESFORCE_MAIN.CASE</b> ·
  Types: Product Onboarding + Onboarding New Restaurant · A launch = <code>GO_LIVE_COMPLETED_DATE_C</code>.<br>
  <b>Bounty tiers</b> are set by <code>COALESCE(ONBOARDING_START_DATE_C, CREATED_DATE)</code> — March 2026
  and older = $40, April–May 2026 = $20, June 2026 onward = no bounty. Payouts count August launches only.
  The COALESCE matters: 59 open aged cases have a null onboarding start date and were being dropped
  by an earlier version of this pull.<br>
  <b>Activation</b> = launched ÷ all cases assigned that month, per Brian's definition. Open, canceled
  and DQ'd cases remain in the denominator.<br>
  <b>Scope:</b> the seven participating pods only — Adam and Andrea (Brian), Edison and Juan Sanabria
  (Dave Candia), Diego Orjuela, Amada Romero and Santiago Romero (Andres Bonilla). Sasan's POS Launch
  org is not in the spiff and is excluded. Cases held by managers themselves, by reps outside these
  pods, or by departed owners are also out of scope.<br>
  Case ownership is a current snapshot — a reassigned case is credited to whoever owns it today.<br>
  Refresh anytime: <code>python3 backlog-bounty/build_dashboard.py</code>
</footer>
</div>

<script>
document.querySelectorAll('.tabs').forEach(function (bar) {{
  bar.addEventListener('click', function (e) {{
    var btn = e.target.closest('.tab');
    if (!btn) return;
    bar.querySelectorAll('.tab').forEach(function (b) {{ b.classList.remove('active'); }});
    btn.classList.add('active');
    var want = btn.dataset.target;
    var table = bar.nextElementSibling.querySelector('table');
    table.querySelectorAll('tbody tr').forEach(function (tr) {{
      tr.style.display = (want === 'all' || tr.dataset.pod === want) ? '' : 'none';
    }});
  }});
}});
</script>
</body></html>"""


def main():
    if "--no-refresh" not in sys.argv:
        run_queries()
    reps = build_model()
    today = dt.date.today()
    html = render(reps, today)
    out = ROOT / f"Backlog_Bounty_{today:%Y-%m-%d}.html"
    out.write_text(html)
    # index.html is what GitHub Pages serves, so it always mirrors the newest build.
    (ROOT / "index.html").write_text(html)
    print(out)


if __name__ == "__main__":
    main()
