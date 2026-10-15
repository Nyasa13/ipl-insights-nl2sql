-- Analytics views. Written in portable SQL (Postgres + DuckDB) so the same file
-- is used in production and in the offline tests.
-- ball_facts is the workhorse: every regular-innings ball with season/venue and
-- the cricket conventions (legal ball, runs charged to bowler, bowler wicket, phase)
-- already encoded, so the LLM does not have to re-derive them.

CREATE VIEW ball_facts AS
SELECT
    d.match_id,
    m.season,
    m.date,
    m.venue,
    m.city,
    d.inning,
    d.batting_team,
    d.bowling_team,
    d.over_no,
    d.ball,
    d.batter,
    d.bowler,
    d.batter_runs,
    d.extra_runs,
    d.total_runs,
    d.extras_type,
    d.is_wicket,
    d.player_dismissed,
    d.dismissal_kind,
    -- runs charged to the bowler: everything except byes, leg byes and penalty runs
    CASE WHEN COALESCE(d.extras_type, '') IN ('byes', 'legbyes', 'penalty')
         THEN d.total_runs - d.extra_runs
         ELSE d.total_runs END AS bowler_runs,
    -- 1 if the wicket is credited to the bowler (excludes run outs, retirements, obstructing the field)
    CASE WHEN d.is_wicket = 1
              AND COALESCE(d.dismissal_kind, '') NOT IN ('run out', 'retired hurt', 'retired out', 'obstructing the field')
         THEN 1 ELSE 0 END AS is_bowler_wicket,
    -- 1 if the ball counts towards the over (not a wide / no ball)
    CASE WHEN COALESCE(d.extras_type, '') IN ('wides', 'noballs') THEN 0 ELSE 1 END AS is_legal_delivery,
    -- 1 if the batter faced the ball (wides are not faced)
    CASE WHEN COALESCE(d.extras_type, '') = 'wides' THEN 0 ELSE 1 END AS is_batter_ball,
    CASE WHEN d.over_no <= 6 THEN 'powerplay'
         WHEN d.over_no <= 15 THEN 'middle'
         ELSE 'death' END AS phase
FROM deliveries d
JOIN matches m ON m.match_id = d.match_id
WHERE d.inning IN (1, 2);   -- exclude super overs (innings 3 and 4)

CREATE VIEW player_match_batting AS
SELECT
    match_id, season, date, batter, batting_team,
    SUM(batter_runs)                                   AS runs,
    SUM(is_batter_ball)                                AS balls_faced,
    SUM(CASE WHEN batter_runs = 4 THEN 1 ELSE 0 END)   AS fours,
    SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END)   AS sixes,
    ROUND(100.0 * SUM(batter_runs) / NULLIF(SUM(is_batter_ball), 0), 2) AS strike_rate
FROM ball_facts
GROUP BY match_id, season, date, batter, batting_team;

CREATE VIEW player_match_bowling AS
SELECT
    match_id, season, date, bowler, bowling_team,
    SUM(is_legal_delivery)                             AS balls,
    SUM(bowler_runs)                                   AS runs_conceded,
    SUM(is_bowler_wicket)                              AS wickets,
    ROUND(6.0 * SUM(bowler_runs) / NULLIF(SUM(is_legal_delivery), 0), 2) AS economy
FROM ball_facts
GROUP BY match_id, season, date, bowler, bowling_team;

CREATE VIEW batting_by_season AS
SELECT
    season, batter,
    COUNT(DISTINCT match_id)                           AS innings,
    SUM(is_batter_ball)                                AS balls_faced,
    SUM(batter_runs)                                   AS runs,
    SUM(CASE WHEN batter_runs = 4 THEN 1 ELSE 0 END)   AS fours,
    SUM(CASE WHEN batter_runs = 6 THEN 1 ELSE 0 END)   AS sixes,
    ROUND(100.0 * SUM(batter_runs) / NULLIF(SUM(is_batter_ball), 0), 2) AS strike_rate
FROM ball_facts
GROUP BY season, batter;

CREATE VIEW bowling_by_season AS
SELECT
    season, bowler,
    COUNT(DISTINCT match_id)                           AS matches_bowled,
    SUM(is_legal_delivery)                             AS balls,
    SUM(bowler_runs)                                   AS runs_conceded,
    SUM(is_bowler_wicket)                              AS wickets,
    ROUND(6.0 * SUM(bowler_runs) / NULLIF(SUM(is_legal_delivery), 0), 2) AS economy
FROM ball_facts
GROUP BY season, bowler;
