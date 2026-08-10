-- Remaining bounty opportunity: OPEN aging cases still sitting in onboarding.
-- These are the cases that (a) still carry a bounty if launched before 8/31, and
-- (b) face the forced-churn rule if they're 3+ months old and still open at EOM.

SELECT
  u.ID                       AS owner_id,
  u.NAME                     AS rep,
  mgr.NAME                   AS manager,
  c.CASE_NUMBER              AS case_number,
  a.NAME                     AS account_name,
  c.STATUS                   AS status,
  COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE)  AS onboarding_start,
  TO_CHAR(COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE),'YYYY-MM') AS cohort_month,
  DATEDIFF(day, COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE), CURRENT_DATE) AS days_open,
  c.GO_LIVE_SCHEDULED_DATE_C AS go_live_scheduled,
  c.LAUNCH_CONFIDENCE_LEVEL_C AS launch_confidence,
  CASE
    WHEN COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) <  '2026-04-01' THEN 40
    WHEN COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) <= '2026-05-31' THEN 20
    ELSE 0
  END                        AS bounty_if_launched
FROM PC_FIVETRAN_DB.SALESFORCE_MAIN.CASE c
JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.USER u   ON u.ID = c.OWNER_ID
LEFT JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.USER mgr ON mgr.ID = u.MANAGER_ID
LEFT JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.ACCOUNT a ON a.ID = c.ACCOUNT_ID
WHERE c.TYPE IN ('Product Onboarding','Onboarding New Restaurant')
  AND c.IS_DELETED = FALSE
  AND c.IS_CLOSED = FALSE
  AND COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) <= '2026-05-31'
ORDER BY manager, rep, onboarding_start;
