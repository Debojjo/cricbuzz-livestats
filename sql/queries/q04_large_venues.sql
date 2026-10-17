-- Q4 (Beginner): Venues with a seating capacity of more than 50,000.
-- Show venue name, city, country and capacity, largest first.
--
-- Business use: planning, ticketing and "biggest grounds" features.
-- Capacity comes from the API where it exists and from data/venues_extra.csv
-- (approximate public figures) for well-known stadiums. Unknown capacity (NULL)
-- never passes the > test, so those venues are simply left out.

SELECT
    venue_name,
    city,
    country,
    capacity
FROM venues
WHERE capacity > 50000
ORDER BY capacity DESC, venue_name;
