"""Dynamic prompt context: real values pulled from the database (teams, seasons, categorical values,
well-known player spellings). Cached for the life of the process."""
from __future__ import annotations


class SchemaContext:
    def __init__(self, db):
        self.db = db
        self._text: str | None = None
        self._players: list[str] | None = None

    def _col(self, sql: str) -> list:
        return [r[0] for r in self.db.run(sql)[1]]

    def text(self) -> str:
        if self._text is not None:
            return self._text
        try:
            teams = self._col("SELECT team FROM (SELECT team1 AS team FROM matches UNION SELECT team2 FROM matches) t ORDER BY 1")
            seasons = self.db.run("SELECT MIN(season), MAX(season) FROM matches")[1][0]
            toss = self._col("SELECT DISTINCT toss_decision FROM matches WHERE toss_decision IS NOT NULL")
            results = self._col("SELECT DISTINCT result FROM matches WHERE result IS NOT NULL")
            extras = self._col("SELECT DISTINCT extras_type FROM deliveries WHERE extras_type IS NOT NULL")
            kinds = self._col("SELECT DISTINCT dismissal_kind FROM deliveries WHERE dismissal_kind IS NOT NULL")
            venues = self._col("SELECT venue FROM matches WHERE venue IS NOT NULL GROUP BY venue ORDER BY COUNT(*) DESC LIMIT 25")
            bat = self._col("SELECT batter FROM batting_by_season GROUP BY batter ORDER BY SUM(runs) DESC LIMIT 30")
            bowl = self._col("SELECT bowler FROM bowling_by_season GROUP BY bowler ORDER BY SUM(wickets) DESC LIMIT 30")
            self._text = (
                "ACTUAL VALUES IN THE DATABASE\n"
                f"seasons: {seasons[0]}-{seasons[1]}\n"
                f"teams: {', '.join(teams)}\n"
                f"toss_decision: {toss}\nresult: {results}\nextras_type: {extras}\ndismissal_kind: {kinds}\n"
                f"most-used venues: {'; '.join(venues)}\n"
                f"sample batter names: {', '.join(bat)}\nsample bowler names: {', '.join(bowl)}"
            )
        except Exception:
            self._text = ""
        return self._text

    def players(self) -> list[str]:
        if self._players is None:
            try:
                self._players = self._col(
                    "SELECT batter FROM batting_by_season UNION SELECT bowler FROM bowling_by_season")
            except Exception:
                self._players = []
        return self._players
