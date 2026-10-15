"""Entity linking: map names the user types ("Virat Kohli", "RCB") to the exact strings in the database
("V Kohli", "Royal Challengers Bengaluru") and pass them to the LLM as hints."""
from __future__ import annotations

import re
from collections import defaultdict

TEAM_ALIASES = {
    # abbreviations are matched case-sensitively, full names case-insensitively
    "CSK": "Chennai Super Kings", "Chennai Super Kings": "Chennai Super Kings", "Chennai": "Chennai Super Kings",
    "MI": "Mumbai Indians", "Mumbai Indians": "Mumbai Indians",
    "KKR": "Kolkata Knight Riders", "Kolkata Knight Riders": "Kolkata Knight Riders", "Kolkata": "Kolkata Knight Riders",
    "RCB": "Royal Challengers Bengaluru", "Royal Challengers Bangalore": "Royal Challengers Bengaluru",
    "Royal Challengers Bengaluru": "Royal Challengers Bengaluru", "Bangalore": "Royal Challengers Bengaluru",
    "DC": "Delhi Capitals", "Delhi Capitals": "Delhi Capitals", "Delhi Daredevils": "Delhi Capitals",
    "PBKS": "Punjab Kings", "KXIP": "Punjab Kings", "Punjab Kings": "Punjab Kings", "Kings XI Punjab": "Punjab Kings",
    "RR": "Rajasthan Royals", "Rajasthan Royals": "Rajasthan Royals",
    "SRH": "Sunrisers Hyderabad", "Sunrisers Hyderabad": "Sunrisers Hyderabad",
    "GT": "Gujarat Titans", "Gujarat Titans": "Gujarat Titans",
    "LSG": "Lucknow Super Giants", "Lucknow Super Giants": "Lucknow Super Giants",
    "Deccan Chargers": "Deccan Chargers", "Gujarat Lions": "Gujarat Lions", "Pune Warriors": "Pune Warriors",
    "Rising Pune Supergiant": "Rising Pune Supergiant", "Rising Pune Supergiants": "Rising Pune Supergiant",
}
_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")


class EntityLinker:
    def __init__(self, players: list[str]):
        self.by_surname: dict[str, list[str]] = defaultdict(list)
        for p in players:
            if p and p.split():
                self.by_surname[p.split()[-1].lower()].append(p)

    def team_hints(self, question: str) -> list[str]:
        hints = []
        for alias, canon in TEAM_ALIASES.items():
            if alias == canon:
                continue
            flags = 0 if alias.isupper() and len(alias) <= 5 else re.I
            if re.search(rf"\b{re.escape(alias)}\b", question, flags):
                hints.append(f"'{alias}' -> team name '{canon}'")
        return hints

    def player_hints(self, question: str) -> list[str]:
        tokens = [(m.group(0), m.start()) for m in _WORD.finditer(question)]
        hints, seen = [], set()
        for i, (tok, _) in enumerate(tokens):
            if not tok[0].isupper():
                continue
            cands = self.by_surname.get(tok.lower())
            if not cands:
                continue
            prev = tokens[i - 1][0] if i > 0 and tokens[i - 1][0][0].isupper() else None
            chosen, used_prev = cands, False
            if prev:
                p = prev.lower()
                initials = lambda c: "".join(c.split()[:-1]).lower()  # "RG Sharma" -> "rg"
                exact = [c for c in cands if initials(c) == p]
                narrowed = [c for c in cands if initials(c).startswith(p[0])]
                chosen = exact or narrowed or cands
                used_prev = bool(exact or narrowed)
            if len(chosen) > 4:
                continue
            label = f"{prev} {tok}" if used_prev else tok
            key = tuple(chosen)
            if key in seen:
                continue
            seen.add(key)
            if len(chosen) == 1:
                hints.append(f"'{label}' -> player name '{chosen[0]}'")
            else:
                hints.append(f"'{label}' could be: " + ", ".join(f"'{c}'" for c in chosen))
        return hints

    def hints(self, question: str) -> list[str]:
        return self.team_hints(question) + self.player_hints(question)
