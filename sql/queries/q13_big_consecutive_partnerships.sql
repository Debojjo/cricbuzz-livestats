-- Q13 (Intermediate): Partnerships of 100+ runs between consecutive batsmen.
-- "Consecutive" = batting positions next to each other (for example #3 and #4).
-- Show both players, the partnership runs and the innings.
--
-- v_partnership_detail (views.sql) joins each partnership to both batters'
-- positions and sets is_consecutive = 1 when they differ by exactly 1. A
-- partnership between #1 and #3 (after #2 was out) is NOT consecutive, as the
-- question defines it. Exactly 100 runs qualifies (100 or more).

SELECT
    bat1_name   AS batsman_1,
    bat2_name   AS batsman_2,
    runs        AS partnership_runs,
    innings_no  AS innings,
    match_id,
    match_date
FROM v_partnership_detail
WHERE is_consecutive = 1
  AND runs >= 100
ORDER BY runs DESC, match_date DESC, match_id;
