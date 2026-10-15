-- Tables + indexes. Run by db/load_data.py (Postgres).
-- Views live in db/views.sql (portable SQL so they are also tested on DuckDB).

DROP VIEW IF EXISTS player_match_batting CASCADE;
DROP VIEW IF EXISTS player_match_bowling CASCADE;
DROP VIEW IF EXISTS batting_by_season CASCADE;
DROP VIEW IF EXISTS bowling_by_season CASCADE;
DROP VIEW IF EXISTS ball_facts CASCADE;
DROP TABLE IF EXISTS deliveries CASCADE;
DROP TABLE IF EXISTS matches CASCADE;

CREATE TABLE matches (
    match_id        INTEGER PRIMARY KEY,
    season          INTEGER NOT NULL,          -- calendar year of the match date (IPL 2008 = 2008)
    date            DATE    NOT NULL,
    city            TEXT,
    venue           TEXT,
    match_type      TEXT,                      -- League / Qualifier 1 / Eliminator / Final ...
    team1           TEXT NOT NULL,
    team2           TEXT NOT NULL,
    toss_winner     TEXT,
    toss_decision   TEXT,                      -- 'bat' | 'field'
    winner          TEXT,                      -- NULL when no result
    result          TEXT,                      -- 'runs' | 'wickets' | 'tie' | 'no result'
    result_margin   NUMERIC,
    target_runs     NUMERIC,
    target_overs    NUMERIC,
    super_over      TEXT,                      -- 'Y' | 'N'
    player_of_match TEXT
);

CREATE TABLE deliveries (
    delivery_id      BIGSERIAL PRIMARY KEY,
    match_id         INTEGER NOT NULL REFERENCES matches(match_id),
    inning           SMALLINT NOT NULL,        -- 1,2 regular; 3,4 super over
    batting_team     TEXT NOT NULL,
    bowling_team     TEXT NOT NULL,
    over_no          SMALLINT NOT NULL,        -- 1..20 (1-indexed)
    ball             SMALLINT NOT NULL,        -- ball number within the over (can exceed 6 with extras)
    batter           TEXT NOT NULL,
    bowler           TEXT NOT NULL,
    non_striker      TEXT,
    batter_runs      SMALLINT NOT NULL,
    extra_runs       SMALLINT NOT NULL,
    total_runs       SMALLINT NOT NULL,
    extras_type      TEXT,                     -- wides | noballs | byes | legbyes | penalty | NULL
    is_wicket        SMALLINT NOT NULL,        -- 0/1
    player_dismissed TEXT,
    dismissal_kind   TEXT,
    fielder          TEXT
);

CREATE INDEX idx_matches_season     ON matches(season);
CREATE INDEX idx_matches_winner     ON matches(winner);
CREATE INDEX idx_deliveries_match   ON deliveries(match_id);
CREATE INDEX idx_deliveries_batter  ON deliveries(batter);
CREATE INDEX idx_deliveries_bowler  ON deliveries(bowler);
CREATE INDEX idx_deliveries_over    ON deliveries(over_no);
