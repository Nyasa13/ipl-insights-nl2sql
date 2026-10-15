"""Generate a small FAKE IPL dataset in the Kaggle CSV format.

Only for trying the pipeline and for offline tests. The numbers mean nothing:
never put results computed on this data on your resume.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TEAMS = [
    "Chennai Super Kings", "Mumbai Indians", "Kolkata Knight Riders", "Royal Challengers Bangalore",
    "Delhi Daredevils", "Kings XI Punjab", "Rajasthan Royals", "Sunrisers Hyderabad",
]
VENUES = ["Wankhede Stadium", "MA Chidambaram Stadium", "Eden Gardens", "M Chinnaswamy Stadium",
          "Arun Jaitley Stadium", "Narendra Modi Stadium"]
KNOWN = {"Royal Challengers Bangalore": ["V Kohli", "AB de Villiers"], "Mumbai Indians": ["RG Sharma", "JJ Bumrah"],
         "Chennai Super Kings": ["MS Dhoni"]}
INITIALS = list("ABCDEFGHIJKLMNPRSTUVY")
SURNAMES = ["Patel", "Singh", "Khan", "Kumar", "Yadav", "Reddy", "Nair", "Gupta", "Iyer", "Verma", "Das",
            "Mishra", "Pandey", "Rana", "Thakur", "Chahar", "Sen", "Roy", "Bose", "Shah", "Rao", "Jain"]
OUTCOMES = [0, 1, 2, 4, 6, "W"]
P_BAT = [0.34, 0.36, 0.08, 0.10, 0.07, 0.05]


def _squads(rng):
    squads, used = {}, set(n for v in KNOWN.values() for n in v)
    for t in TEAMS:
        names = list(KNOWN.get(t, []))
        while len(names) < 14:
            n = f"{rng.choice(INITIALS)} {rng.choice(SURNAMES)}"
            if n not in used:
                used.add(n)
                names.append(n)
        squads[t] = names
    return squads


def _innings(rng, bat, bowl, squads, match_id, inning, target=None, max_overs=20, max_balls=None):
    rows, score, wkts = [], 0, 0
    order = squads[bat][:11]
    bowlers = squads[bowl][3:11]
    striker, non, nxt = order[0], order[1], 2
    balls_bowled = 0
    for ov in range(max_overs):
        bowler = bowlers[ov % len(bowlers)]
        ball_no, legal = 0, 0
        while legal < 6:
            if max_balls is not None and balls_bowled >= max_balls:
                return rows, score
            ball_no += 1
            extras_type, extra, bat_runs, wicket, kind, out = None, 0, 0, 0, None, None
            if rng.random() < 0.05:
                extras_type = str(rng.choice(["wides", "noballs", "legbyes", "byes"], p=[.5, .15, .2, .15]))
                extra = 1 if extras_type in ("wides", "noballs") else int(rng.integers(1, 3))
            else:
                o = rng.choice(len(OUTCOMES), p=P_BAT)
                if OUTCOMES[o] == "W":
                    wicket, out = 1, striker
                    kind = str(rng.choice(["caught", "bowled", "lbw", "run out"], p=[.6, .2, .12, .08]))
                else:
                    bat_runs = OUTCOMES[o]
            total = bat_runs + extra
            rows.append(dict(match_id=match_id, inning=inning, batting_team=bat, bowling_team=bowl, over=ov,
                             ball=ball_no, batter=striker, bowler=bowler, non_striker=non, batsman_runs=bat_runs,
                             extra_runs=extra, total_runs=total, extras_type=extras_type, is_wicket=wicket,
                             player_dismissed=out, dismissal_kind=kind, fielder=None))
            score += total
            if extras_type not in ("wides", "noballs"):
                legal += 1
                balls_bowled += 1
            if wicket:
                wkts += 1
                if wkts >= 10 or nxt >= len(order):
                    return rows, score
                striker, nxt = order[nxt], nxt + 1
            elif (bat_runs % 2 == 1):
                striker, non = non, striker
            if target is not None and score >= target:
                return rows, score
        striker, non = non, striker
    return rows, score


def make(seed: int = 7, seasons=range(2008, 2025), matches_per_season: int = 36):
    rng = np.random.default_rng(seed)
    squads = _squads(rng)
    m_rows, d_rows, mid = [], [], 1000
    for season in seasons:
        for k in range(matches_per_season):
            mid += 1
            t1, t2 = rng.choice(TEAMS, 2, replace=False)
            venue = str(rng.choice(VENUES))
            toss = str(rng.choice([t1, t2]))
            decision = str(rng.choice(["bat", "field"]))
            first, second = (toss, t2 if toss == t1 else t1) if decision == "bat" else ((t2 if toss == t1 else t1), toss)
            r1, s1 = _innings(rng, first, second, squads, mid, 1)
            r2, s2 = _innings(rng, second, first, squads, mid, 2, target=s1 + 1)
            d_rows += r1 + r2
            super_over, result, winner, margin = "N", "runs", first, s1 - s2
            if s2 > s1:
                result, winner = "wickets", second
                margin = 10 - sum(1 for r in r2 if r["is_wicket"])
            elif s2 == s1:
                super_over = "Y"
                so1, a = _innings(rng, first, second, squads, mid, 3, max_overs=1)
                so2, b = _innings(rng, second, first, squads, mid, 4, max_overs=1)
                d_rows += so1 + so2
                winner, result, margin = (first if a >= b else second), "runs", 0
            date = pd.Timestamp(year=season, month=4, day=1) + pd.Timedelta(days=int(k * 1.5))
            m_rows.append(dict(
                id=mid, season=str(season), city="Test City", date=date.strftime("%Y-%m-%d"), match_type="League",
                player_of_match=squads[winner][0], venue=venue, team1=t1, team2=t2, toss_winner=toss,
                toss_decision=decision, winner=winner, result=result, result_margin=margin,
                target_runs=s1 + 1, target_overs=20, super_over=super_over, method=None,
                umpire1="U1", umpire2="U2"))
    d = pd.DataFrame(d_rows).rename(columns={})
    return pd.DataFrame(m_rows), d


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "data/synthetic"
    import os
    os.makedirs(out, exist_ok=True)
    m, d = make()
    m.to_csv(f"{out}/matches.csv", index=False)
    d.to_csv(f"{out}/deliveries.csv", index=False)
    print(len(m), "matches", len(d), "deliveries ->", out)
