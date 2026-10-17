-- Q8 (Beginner): Cricket series that started in 2024.
-- Show series name, host country, match type, start date and planned matches.
--
-- The series archive gives only a name and dates. Host country and match type are
-- filled from the name when it says so (see data/enrich.py), otherwise they show
-- 'Not stated'. The planned number of matches is not in the archive data, so it
-- stays empty (NULL) unless we have loaded that series' matches.
-- Dates are ISO text, so a half-open range selects exactly the calendar year.

SELECT
    series_name,
    COALESCE(host_country, 'Not stated') AS host_country,
    COALESCE(match_type,   'Not stated') AS match_type,
    start_date,
    total_matches
FROM series
WHERE start_date >= '2024-01-01'
  AND start_date <  '2025-01-01'
ORDER BY start_date, series_name;
