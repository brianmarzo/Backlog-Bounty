-- Per-case detail behind every cell of the activation matrix.
--
-- The matrix says "26/38 launched". This query returns the OTHER 12 — the cases that
-- make up the gap between LAUNCHED and ASSIGNED for each rep x cohort month, so a cell
-- can be opened up and worked as a list instead of just read as a percentage.
--
-- Launched cases are deliberately excluded: they're the numerator, they need no action,
-- and including them would multiply the payload ~3x for no decision value.
--
-- Cohort month and the bounty tier use the same COALESCE(onboarding start, created) rule
-- as every other query here, so the drill-down always reconciles to the matrix.

SELECT
  u.NAME     AS rep,
  mgr.NAME   AS manager,
  CASE
    WHEN COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) < '2026-01-01' THEN 'pre-2026'
    ELSE TO_CHAR(COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE),'YYYY-MM')
  END        AS cohort_month,
  c.CASE_NUMBER              AS case_number,
  a.NAME                     AS account_name,
  c.STATUS                   AS status,
  -- Three-way disposition: what actually happened to this case.
  CASE
    WHEN c.IS_CLOSED = FALSE      THEN 'Open'
    WHEN c.STATUS = 'Canceled'    THEN 'Canceled'
    ELSE 'Closed - not launched'
  END                        AS disposition,
  DATEDIFF(day, COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE), CURRENT_DATE) AS days_open,
  c.GO_LIVE_SCHEDULED_DATE_C  AS go_live_scheduled,
  c.LAUNCH_CONFIDENCE_LEVEL_C AS launch_confidence,
  c.ONBOARDING_PAUSED_REASON_C AS paused_reason,
  -- Only OPEN cases can still be launched for money before 8/31.
  CASE
    WHEN c.IS_CLOSED = TRUE THEN 0
    WHEN COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) <  '2026-04-01' THEN 40
    WHEN COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) <= '2026-05-31' THEN 20
    ELSE 0
  END                        AS bounty_if_launched
FROM PC_FIVETRAN_DB.SALESFORCE_MAIN.CASE c
JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.USER u        ON u.ID = c.OWNER_ID
LEFT JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.USER mgr ON mgr.ID = u.MANAGER_ID
LEFT JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.ACCOUNT a ON a.ID = c.ACCOUNT_ID
WHERE c.TYPE IN ('Product Onboarding','Onboarding New Restaurant')
  AND c.IS_DELETED = FALSE
  AND c.GO_LIVE_COMPLETED_DATE_C IS NULL
  AND COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) IS NOT NULL
  AND COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) <= '2026-07-31'
ORDER BY manager, rep, cohort_month, days_open DESC;
