-- Backlog Bounty (August 2026) — case-level August launches with cohort + bounty value.
--
-- Bounty rules (per the spiff announcement):
--   $40  per case launched in August whose onboarding cohort is MARCH 2026 or earlier
--   $20  per case launched in August whose onboarding cohort is APRIL or MAY 2026
--   $0   for June 2026+ cohorts (not backlog)
--
-- Cohort field = COALESCE(ONBOARDING_START_DATE_C, CREATED_DATE).
-- ONBOARDING_START_DATE_C alone is 100% populated on August launches, but 59 currently-OPEN
-- aged cases have it NULL — using it bare silently dropped them from the backlog count
-- (541 instead of 600). Falling back to CREATED_DATE keeps those cases in scope.
--
-- Launch = GO_LIVE_COMPLETED_DATE_C set within the August window.

SELECT
  u.ID                                AS owner_id,
  u.NAME                              AS rep,
  u.TITLE                             AS title,
  mgr.NAME                            AS manager,
  c.ID                                AS case_id,
  c.CASE_NUMBER                       AS case_number,
  a.NAME                              AS account_name,
  c.TYPE                              AS case_type,
  COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE)           AS onboarding_start,
  TO_CHAR(COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE),'YYYY-MM') AS cohort_month,
  c.GO_LIVE_COMPLETED_DATE_C          AS launched_on,
  DATEDIFF(day, COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE), c.GO_LIVE_COMPLETED_DATE_C) AS days_in_onboarding,
  c.CASE_LAUNCH_GP_SCORE_C            AS gp_score,
  CASE
    WHEN COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) <  '2026-04-01' THEN 40
    WHEN COALESCE(c.ONBOARDING_START_DATE_C, c.CREATED_DATE::DATE) <= '2026-05-31' THEN 20
    ELSE 0
  END                                 AS bounty_usd
FROM PC_FIVETRAN_DB.SALESFORCE_MAIN.CASE c
JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.USER u   ON u.ID = c.OWNER_ID
LEFT JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.USER mgr ON mgr.ID = u.MANAGER_ID
LEFT JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.ACCOUNT a ON a.ID = c.ACCOUNT_ID
WHERE c.TYPE IN ('Product Onboarding','Onboarding New Restaurant')
  AND c.IS_DELETED = FALSE
  AND c.GO_LIVE_COMPLETED_DATE_C BETWEEN '2026-08-01' AND '2026-08-31'
ORDER BY manager, rep, bounty_usd DESC, onboarding_start;
