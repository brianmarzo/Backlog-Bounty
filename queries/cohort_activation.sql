-- Activation rate by ASSIGNMENT COHORT MONTH, per rep. Whole Launch org.
--
-- Brian's definition (confirmed 2026-08-09):
--   Denominator = every case ASSIGNED to the rep in that month.
--   Numerator   = how many of those have launched (GO_LIVE_COMPLETED_DATE_C set), as of today.
--   Cases still open, canceled, or DQ'd stay in the denominator. Nothing is excluded.
--
-- This is deliberately NOT the closed-case activation rate. Early months should be
-- close to final; Jun/Jul cohorts are still maturing and will read low by design.
--
-- Cohort month = COALESCE(ONBOARDING_START_DATE_C, CREATED_DATE) — same rule that sets the
-- bounty tier. The COALESCE matters: 59 open aged cases have a NULL onboarding start date.
-- Caveat: OWNER_ID is a current snapshot — a reassigned case lands on today's owner.

SELECT
  u.ID       AS owner_id,
  u.NAME     AS rep,
  u.TITLE    AS title,
  mgr.NAME   AS manager,
  CASE
    WHEN COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) < '2026-01-01' THEN 'pre-2026'
    ELSE TO_CHAR(COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE),'YYYY-MM')
  END        AS cohort_month,
  COUNT(*)   AS assigned,
  COUNT(c.GO_LIVE_COMPLETED_DATE_C)                                        AS launched,
  COUNT_IF(c.IS_CLOSED = FALSE)                                            AS still_open,
  COUNT_IF(c.STATUS = 'Canceled')                                          AS canceled,
  COUNT_IF(c.IS_CLOSED = TRUE
           AND c.GO_LIVE_COMPLETED_DATE_C IS NULL
           AND c.STATUS <> 'Canceled')                                     AS closed_other,
  ROUND(100.0 * COUNT(c.GO_LIVE_COMPLETED_DATE_C) / NULLIF(COUNT(*),0), 1) AS activation_pct
FROM PC_FIVETRAN_DB.SALESFORCE_MAIN.CASE c
JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.USER u        ON u.ID = c.OWNER_ID
LEFT JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.USER mgr ON mgr.ID = u.MANAGER_ID
WHERE c.TYPE IN ('Product Onboarding','Onboarding New Restaurant')
  AND c.IS_DELETED = FALSE
  AND COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) IS NOT NULL
  AND COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) <= '2026-07-31'
GROUP BY 1,2,3,4,5
ORDER BY manager, rep, cohort_month;
