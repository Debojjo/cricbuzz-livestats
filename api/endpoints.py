"""Endpoint URL templates, in one place.

``{slots}`` are filled from the request parameters; every other parameter goes
into the query string. These paths were copied from the RapidAPI snippets by
the project owner. If a live call ever returns a surprising shape, this is the
only file that needs to change.
"""

MATCHES_RECENT = "matches/v1/recent"
MATCHES_LIVE = "matches/v1/live"  # URL pattern assumed from MATCHES_RECENT; verify
MATCH_INFO = "mcenter/v1/{matchId}"
SCORECARD = "mcenter/v1/{matchId}/scard"
PLAYER_INFO = "stats/v1/player/{playerId}"
PLAYER_BATTING = "stats/v1/player/{playerId}/batting"
PLAYER_BOWLING = "stats/v1/player/{playerId}/bowling"
VENUE_INFO = "venues/v1/{venueId}"
RECORDS = "stats/v1/topstats/{id}"
TEAMS_LIST = "teams/v1/international"
TEAM_PLAYERS = "teams/v1/{teamId}/players"
SERIES_ARCHIVES = "series/v1/archives/{type}"
