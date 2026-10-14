-- =============================================================================
-- Cricbuzz LiveStats - database schema (SQLite dialect)
--
-- Conventions
--   * Primary keys reuse Cricbuzz ids, so re-running an import updates rows
--     instead of duplicating them.
--   * Dates are ISO text (YYYY-MM-DD) so sorting and comparing works.
--   * is_sample = 1 marks rows created by the seed script (NOT real API data).
--   * format codes are the same everywhere: 'TEST', 'ODI', 'T20'.
--     (In player_career_stats, 'T20' holds the T20 International column.)
-- SQLite-specific bits (AUTOINCREMENT, PRAGMA) live only in this file and in
-- utils/db_connection.py.
-- =============================================================================

PRAGMA foreign_keys = ON;

-- ----------------------------------------------------------------- teams ----
CREATE TABLE IF NOT EXISTS teams (
    team_id     INTEGER PRIMARY KEY,
    team_name   TEXT    NOT NULL,
    short_name  TEXT,
    country     TEXT,   -- NULL for club / domestic teams
    team_type   TEXT    CHECK (team_type IS NULL OR team_type IN
                    ('international','associate','domestic','league',
                     'women','youth','other')),
    is_sample   INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1))
);

-- --------------------------------------------------------------- players ----
CREATE TABLE IF NOT EXISTS players (
    player_id      INTEGER PRIMARY KEY,
    full_name      TEXT    NOT NULL,
    display_name   TEXT,
    country        TEXT,
    playing_role   TEXT,
    batting_style  TEXT,
    bowling_style  TEXT,
    date_of_birth  DATE,
    birth_place    TEXT,
    is_sample      INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1))
);

-- ---------------------------------------------------------------- venues ----
CREATE TABLE IF NOT EXISTS venues (
    venue_id    INTEGER PRIMARY KEY,
    venue_name  TEXT    NOT NULL,
    city        TEXT,
    country     TEXT,
    capacity    INTEGER CHECK (capacity IS NULL OR capacity > 0),
    is_sample   INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1))
);

-- ---------------------------------------------------------------- series ----
CREATE TABLE IF NOT EXISTS series (
    series_id      INTEGER PRIMARY KEY,
    series_name    TEXT    NOT NULL,
    host_country   TEXT,
    match_type     TEXT,
    start_date     DATE,
    end_date       DATE,
    total_matches  INTEGER CHECK (total_matches IS NULL OR total_matches >= 0),
    is_sample      INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1))
);

-- --------------------------------------------------------------- matches ----
CREATE TABLE IF NOT EXISTS matches (
    match_id        INTEGER PRIMARY KEY,
    series_id       INTEGER REFERENCES series(series_id),
    match_desc      TEXT,
    format          TEXT    NOT NULL CHECK (format IN ('TEST','ODI','T20')),
    match_category  TEXT    CHECK (match_category IS NULL OR match_category IN
                        ('international','league','domestic','women')),
    match_date      DATE,
    venue_id        INTEGER REFERENCES venues(venue_id),
    team1_id        INTEGER NOT NULL REFERENCES teams(team_id),
    team2_id        INTEGER NOT NULL REFERENCES teams(team_id),
    toss_winner_id  INTEGER REFERENCES teams(team_id),
    toss_decision   TEXT    CHECK (toss_decision IS NULL OR
                                   toss_decision IN ('bat','bowl')),
    winner_id       INTEGER REFERENCES teams(team_id),
    victory_margin  INTEGER CHECK (victory_margin IS NULL OR victory_margin >= 0),
    victory_type    TEXT    CHECK (victory_type IS NULL OR victory_type IN
                        ('runs','wickets','innings','draw','tie',
                         'no result','abandoned','forfeit')),
    state           TEXT,
    status          TEXT,
    is_sample       INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1)),
    CHECK (team1_id <> team2_id),
    CHECK (winner_id IS NULL OR winner_id IN (team1_id, team2_id)),
    CHECK (toss_winner_id IS NULL OR toss_winner_id IN (team1_id, team2_id))
);

-- -------------------------------------------------- batting_performances ----
CREATE TABLE IF NOT EXISTS batting_performances (
    performance_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id          INTEGER NOT NULL REFERENCES matches(match_id),
    innings_no        INTEGER NOT NULL CHECK (innings_no >= 1),
    player_id         INTEGER NOT NULL REFERENCES players(player_id),
    team_id           INTEGER NOT NULL REFERENCES teams(team_id),
    batting_position  INTEGER CHECK (batting_position IS NULL OR
                                     batting_position BETWEEN 1 AND 11),
    runs              INTEGER NOT NULL CHECK (runs >= 0),
    balls_faced       INTEGER CHECK (balls_faced IS NULL OR balls_faced >= 0),
    fours             INTEGER NOT NULL DEFAULT 0 CHECK (fours >= 0),
    sixes             INTEGER NOT NULL DEFAULT 0 CHECK (sixes >= 0),
    strike_rate       REAL,
    is_not_out        INTEGER NOT NULL DEFAULT 0 CHECK (is_not_out IN (0, 1)),
    out_desc          TEXT,
    is_sample         INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1)),
    UNIQUE (match_id, innings_no, player_id)
);

-- --------------------------------------------------- bowling_performances ----
-- 'balls' is the reliable figure (overs "3.5" means 3 overs 5 balls = 23 balls).
CREATE TABLE IF NOT EXISTS bowling_performances (
    performance_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(match_id),
    innings_no      INTEGER NOT NULL CHECK (innings_no >= 1),
    player_id       INTEGER NOT NULL REFERENCES players(player_id),
    team_id         INTEGER NOT NULL REFERENCES teams(team_id),
    overs           REAL,
    balls           INTEGER NOT NULL CHECK (balls >= 0),
    maidens         INTEGER NOT NULL DEFAULT 0 CHECK (maidens >= 0),
    runs_conceded   INTEGER NOT NULL CHECK (runs_conceded >= 0),
    wickets         INTEGER NOT NULL DEFAULT 0 CHECK (wickets BETWEEN 0 AND 10),
    economy         REAL,
    is_sample       INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1)),
    UNIQUE (match_id, innings_no, player_id)
);

-- -------------------------------------------------- fielding_performances ----
CREATE TABLE IF NOT EXISTS fielding_performances (
    performance_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(match_id),
    player_id       INTEGER NOT NULL REFERENCES players(player_id),
    catches         INTEGER NOT NULL DEFAULT 0 CHECK (catches >= 0),
    stumpings       INTEGER NOT NULL DEFAULT 0 CHECK (stumpings >= 0),
    is_sample       INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1)),
    UNIQUE (match_id, player_id)
);

-- --------------------------------------------------------- partnerships ----
-- wicket_no = order of the partnership in the innings (1st wicket = 1).
-- Batting positions are NOT stored here; views join them from
-- batting_performances, which is how Q13 / Q24 find consecutive batsmen.
CREATE TABLE IF NOT EXISTS partnerships (
    partnership_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL REFERENCES matches(match_id),
    innings_no      INTEGER NOT NULL CHECK (innings_no >= 1),
    wicket_no       INTEGER NOT NULL CHECK (wicket_no BETWEEN 1 AND 10),
    bat1_id         INTEGER NOT NULL REFERENCES players(player_id),
    bat2_id         INTEGER NOT NULL REFERENCES players(player_id),
    runs            INTEGER NOT NULL CHECK (runs >= 0),
    balls           INTEGER CHECK (balls IS NULL OR balls >= 0),
    is_sample       INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1)),
    CHECK (bat1_id <> bat2_id),
    UNIQUE (match_id, innings_no, wicket_no)
);

-- ---------------------------------------------------- player_career_stats ----
CREATE TABLE IF NOT EXISTS player_career_stats (
    stat_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       INTEGER NOT NULL REFERENCES players(player_id),
    format          TEXT    NOT NULL CHECK (format IN ('TEST','ODI','T20')),
    matches_played  INTEGER NOT NULL DEFAULT 0 CHECK (matches_played >= 0),
    innings         INTEGER NOT NULL DEFAULT 0 CHECK (innings >= 0),
    runs            INTEGER NOT NULL DEFAULT 0 CHECK (runs >= 0),
    balls_faced     INTEGER,
    highest_score   INTEGER CHECK (highest_score IS NULL OR highest_score >= 0),
    batting_avg     REAL,
    strike_rate     REAL,
    not_outs        INTEGER,
    fours           INTEGER,
    sixes           INTEGER,
    ducks           INTEGER,
    fifties         INTEGER,
    centuries       INTEGER,
    wickets         INTEGER NOT NULL DEFAULT 0 CHECK (wickets >= 0),
    bowling_avg     REAL,
    economy_rate    REAL,
    catches         INTEGER NOT NULL DEFAULT 0 CHECK (catches >= 0),
    stumpings       INTEGER NOT NULL DEFAULT 0 CHECK (stumpings >= 0),
    is_sample       INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1)),
    UNIQUE (player_id, format)
);

-- --------------------------------------------------------- api_call_log ----
-- One row per API request (or cache hit). Feeds the "calls remaining" counter
-- and the budget guard, so the 200/month limit is tracked in one place.
CREATE TABLE IF NOT EXISTS api_call_log (
    call_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint     TEXT    NOT NULL,
    params       TEXT,
    status_code  INTEGER,
    from_cache   INTEGER NOT NULL DEFAULT 0 CHECK (from_cache IN (0, 1)),
    called_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- --------------------------------------------------------------- indexes ----
CREATE INDEX IF NOT EXISTS idx_teams_name         ON teams(team_name);
CREATE INDEX IF NOT EXISTS idx_players_country    ON players(country);
CREATE INDEX IF NOT EXISTS idx_players_role       ON players(playing_role);
CREATE INDEX IF NOT EXISTS idx_venues_country     ON venues(country);
CREATE INDEX IF NOT EXISTS idx_venues_capacity    ON venues(capacity);
CREATE INDEX IF NOT EXISTS idx_series_start       ON series(start_date);
CREATE INDEX IF NOT EXISTS idx_matches_date       ON matches(match_date);
CREATE INDEX IF NOT EXISTS idx_matches_format     ON matches(format);
CREATE INDEX IF NOT EXISTS idx_matches_series     ON matches(series_id);
CREATE INDEX IF NOT EXISTS idx_matches_venue      ON matches(venue_id);
CREATE INDEX IF NOT EXISTS idx_matches_team1      ON matches(team1_id);
CREATE INDEX IF NOT EXISTS idx_matches_team2      ON matches(team2_id);
CREATE INDEX IF NOT EXISTS idx_matches_winner     ON matches(winner_id);
CREATE INDEX IF NOT EXISTS idx_bat_player         ON batting_performances(player_id);
CREATE INDEX IF NOT EXISTS idx_bat_match          ON batting_performances(match_id);
CREATE INDEX IF NOT EXISTS idx_bowl_player        ON bowling_performances(player_id);
CREATE INDEX IF NOT EXISTS idx_bowl_match         ON bowling_performances(match_id);
CREATE INDEX IF NOT EXISTS idx_field_player       ON fielding_performances(player_id);
CREATE INDEX IF NOT EXISTS idx_field_match        ON fielding_performances(match_id);
CREATE INDEX IF NOT EXISTS idx_partner_match      ON partnerships(match_id);
CREATE INDEX IF NOT EXISTS idx_partner_bat1       ON partnerships(bat1_id);
CREATE INDEX IF NOT EXISTS idx_partner_bat2       ON partnerships(bat2_id);
CREATE INDEX IF NOT EXISTS idx_career_player      ON player_career_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_career_format      ON player_career_stats(format);
CREATE INDEX IF NOT EXISTS idx_apilog_called      ON api_call_log(called_at);
