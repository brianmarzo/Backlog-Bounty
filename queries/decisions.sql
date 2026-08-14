-- Backlog Bounty — "Decisions" view: are managers running swoops and clearing the pipeline?
--
-- WHY THIS EXISTS: the bounty only pays for launches, so a rep who made 15 hard calls on dead
-- aged cases looks identical to a rep who ignored their backlog entirely — both show $0.
--
-- THE QUESTION THIS ANSWERS (Brian, 2026-08-14): "are we getting rid of cases from our pipeline."
-- A decision is a decision. Launch, DQ, and churn ALL count as good outcomes — Brian is explicit
-- that DQ/cancel is not a bad thing on these aged cases. The only bad outcome is a case nobody
-- touched. Do NOT reintroduce a churn-vs-DQ compliance judgment here; it was built that way on
-- 8/14 and cut the same day.
--
-- BASELINE = the aged backlog as it stood on 2026-08-01: cohort <= 2026-05-31 and not yet
-- resolved before August. This is the inventory managers are being asked to swoop.
--
-- OUTCOME buckets (mutually exclusive, launch wins ties):
--   LAUNCHED   — GO_LIVE_COMPLETED_DATE_C in August. Also earns bounty.
--   CHURNED    — closed in August, churn opp TYPE = 'Pre Live Churn'.
--   DQ         — closed in August, churn opp TYPE = 'Unqualified'.
--   CANCELED_OTHER — closed in August, no churn opp or 'Cancel Relaunch'.
--   ...all four are DECISIONS and are summed together as the headline number.
--   STILL_OPEN — no decision. The only bucket that counts against a rep.
--
-- SWOOP CADENCE: weekly decision counts (W1 = Aug 1–7, W2 = 8–14, W3 = 15–21, W4 = 22–31) plus
-- LAST_DECISION_ON. A pod running real swoops shows decisions in clusters and a recent last-touch;
-- a pod that decided a few cases in week 1 and then went quiet shows a stale last-touch.
--
-- Cohort field = COALESCE(ONBOARDING_START_DATE_C, CREATED_DATE::DATE) — see bounty_cases.sql;
-- using ONBOARDING_START_DATE_C bare drops 59 open aged cases that have it NULL.
--
-- CAVEAT: OWNER_ID is the *current* owner, not the owner on 8/1. A case reassigned mid-month
-- credits its decision to the new owner. Small effect, but don't use this for payout disputes.
--
-- OPENNESS MUST USE IS_CLOSED / CLOSED_DATE, NOT DATE-NULLNESS. Inferring "still open" from
-- (no go-live date AND no cancel date) silently swept in 164 legacy 'Completed' cases closed in
-- 2023–2024 plus 13 stale cancels with a NULL ONBOARDING_CANCELED_DATE_C — inflating the aged
-- baseline from 400 to 577 and "still open" from 306 to 483, which contradicted open_backlog.sql.
-- The STILL_OPEN count here now reconciles to open_backlog.sql by construction.

WITH aged AS (
  SELECT
    c.ID,
    c.OWNER_ID,
    c.CASE_NUMBER,
    a.NAME AS account_name,
    COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) AS onboarding_start,
    c.STATUS,
    c.IS_CLOSED,
    c.CLOSED_DATE::DATE AS closed_on,
    c.GO_LIVE_COMPLETED_DATE_C,
    c.ONBOARDING_CANCELED_DATE_C,
    churn.TYPE AS churn_type,
    CASE
      WHEN COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) <  '2026-04-01' THEN 40
      ELSE 20
    END AS bounty_usd
  FROM PC_FIVETRAN_DB.SALESFORCE_MAIN.CASE c
  LEFT JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.ACCOUNT a       ON a.ID = c.ACCOUNT_ID
  LEFT JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.OPPORTUNITY churn ON churn.ID = c.CHURN_OPPORTUNITY_C
  WHERE c.TYPE IN ('Product Onboarding','Onboarding New Restaurant')
    AND c.IS_DELETED = FALSE
    AND COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) <= '2026-05-31'
    -- in the aged backlog on 2026-08-01: either still open now, or closed during August
    AND (c.IS_CLOSED = FALSE OR c.CLOSED_DATE >= '2026-08-01')
    AND (c.GO_LIVE_COMPLETED_DATE_C IS NULL OR c.GO_LIVE_COMPLETED_DATE_C >= '2026-08-01')
),
classified AS (
  SELECT
    aged.*,
    CASE
      WHEN GO_LIVE_COMPLETED_DATE_C BETWEEN '2026-08-01' AND '2026-08-31' THEN 'LAUNCHED'
      WHEN IS_CLOSED AND closed_on BETWEEN '2026-08-01' AND '2026-08-31'
           AND churn_type = 'Pre Live Churn' THEN 'CHURNED'
      WHEN IS_CLOSED AND closed_on BETWEEN '2026-08-01' AND '2026-08-31'
           AND churn_type = 'Unqualified'    THEN 'DQ'
      WHEN IS_CLOSED AND closed_on BETWEEN '2026-08-01' AND '2026-08-31' THEN 'CANCELED_OTHER'
      ELSE 'STILL_OPEN'
    END AS outcome,
    -- The date the decision landed, whichever kind it was. NULL for still-open cases.
    CASE
      WHEN GO_LIVE_COMPLETED_DATE_C BETWEEN '2026-08-01' AND '2026-08-31'
        THEN GO_LIVE_COMPLETED_DATE_C
      WHEN IS_CLOSED AND closed_on BETWEEN '2026-08-01' AND '2026-08-31'
        THEN closed_on
    END AS decided_on
  FROM aged
)
SELECT
  mgr.NAME AS manager,
  u.NAME   AS rep,
  u.TITLE  AS title,
  COUNT(*)                                                     AS aged_backlog_aug1,
  COUNT_IF(outcome = 'LAUNCHED')                               AS launched,
  COUNT_IF(outcome = 'CHURNED')                                AS churned,
  COUNT_IF(outcome = 'DQ')                                     AS dqd,
  COUNT_IF(outcome = 'CANCELED_OTHER')                         AS canceled_other,
  COUNT_IF(outcome = 'STILL_OPEN')                             AS still_open,
  COUNT_IF(outcome <> 'STILL_OPEN')                            AS decisions,
  ROUND(100.0 * COUNT_IF(outcome <> 'STILL_OPEN') / COUNT(*), 1) AS decision_pct,
  -- Swoop cadence: where in the month the decisions actually landed.
  COUNT_IF(decided_on BETWEEN '2026-08-01' AND '2026-08-07')   AS dec_w1,
  COUNT_IF(decided_on BETWEEN '2026-08-08' AND '2026-08-14')   AS dec_w2,
  COUNT_IF(decided_on BETWEEN '2026-08-15' AND '2026-08-21')   AS dec_w3,
  COUNT_IF(decided_on BETWEEN '2026-08-22' AND '2026-08-31')   AS dec_w4,
  MAX(decided_on)                                              AS last_decision_on,
  DATEDIFF(day, MAX(decided_on), CURRENT_DATE)                 AS days_since_decision,
  SUM(CASE WHEN outcome = 'LAUNCHED' THEN bounty_usd ELSE 0 END) AS bounty_earned,
  SUM(CASE WHEN outcome = 'STILL_OPEN' THEN bounty_usd ELSE 0 END) AS bounty_left
FROM classified
JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.USER u   ON u.ID = classified.OWNER_ID
LEFT JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.USER mgr ON mgr.ID = u.MANAGER_ID
WHERE u.TITLE NOT ILIKE '%POS%'
  AND mgr.NAME IN ('Adam Hubbell','Andrea Novais','Edison Blanco','Juan Sanabria',
                   'Diego Orjuela','Amada Romero','Santiago Romero')
GROUP BY 1,2,3
ORDER BY manager, decision_pct DESC, rep;
