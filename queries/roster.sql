-- Active roster for the seven participating pods.
--
-- The dashboard used to derive its rep list from whoever owned a case, which meant a rep
-- with no aged inventory silently vanished from the standings. Managers read that as a bug
-- (Adam flagged three of his own reps missing), so the rep tables are now roster-driven:
-- every active rep gets a row, even at $0.
--
-- Pod membership comes from USER.MANAGER_ID at query time — the stored roster files go
-- stale fast. POS Launch is excluded; it's a separate org and not in the spiff.
--
-- Note this returns only ACTIVE users. Departed reps who still own open cases are picked
-- up from the case data instead and flagged in the UI, since their cases are still real
-- churn liability that someone has to absorb.

SELECT
  mgr.NAME  AS manager,
  u.NAME    AS rep,
  u.TITLE   AS title
FROM PC_FIVETRAN_DB.SALESFORCE_MAIN.USER u
JOIN PC_FIVETRAN_DB.SALESFORCE_MAIN.USER mgr ON mgr.ID = u.MANAGER_ID
WHERE u.IS_ACTIVE = TRUE
  AND u.TITLE NOT ILIKE '%POS%'
  AND mgr.NAME IN ('Adam Hubbell','Andrea Novais','Edison Blanco','Juan Sanabria',
                   'Diego Orjuela','Amada Romero','Santiago Romero')
ORDER BY manager, rep;
