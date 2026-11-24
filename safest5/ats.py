"""ATS (against the spread) records and the Safest 5 ranking.

The ranking matches the original Safest ATS Picks page: each game's edge is the
home team's Home ATS % minus the away team's Away ATS % (or the reverse), with
overall ATS % as the tiebreak. New here: an early-season blend, so a team with
fewer than `min_games` home (or away) games this season has its split pooled
with last season's split.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Split:
    covers: int = 0
    losses: int = 0
    pushes: int = 0

    @property
    def games(self) -> int:
        return self.covers + self.losses + self.pushes

    @property
    def decisive(self) -> int:
        return self.covers + self.losses

    def pct(self) -> float:
        """Cover %. A team with no decided games yet (e.g. a new club) counts as a neutral 50%."""
        return round(self.covers / self.decisive * 100, 1) if self.decisive else 50.0

    def __add__(self, other: "Split") -> "Split":
        return Split(self.covers + other.covers, self.losses + other.losses, self.pushes + other.pushes)

    def record(self) -> str:
        return f"{self.covers}-{self.losses}-{self.pushes}"


def team_splits(games: pd.DataFrame) -> dict[str, dict[str, Split]]:
    """{team: {'home': Split, 'away': Split}} from rows with an ATS Result."""
    out: dict[str, dict[str, Split]] = {}
    d = games[games["ATS Result"].isin(["Home Cover", "Away Cover", "Push"])]
    for home, away, res in zip(d["Home Team"], d["Away Team"], d["ATS Result"]):
        h = out.setdefault(home, {"home": Split(), "away": Split()})["home"]
        a = out.setdefault(away, {"home": Split(), "away": Split()})["away"]
        if res == "Home Cover":
            h.covers += 1
            a.losses += 1
        elif res == "Away Cover":
            h.losses += 1
            a.covers += 1
        else:
            h.pushes += 1
            a.pushes += 1
    return out


def blended_splits(current: pd.DataFrame, previous: pd.DataFrame | None, min_games: int = 3) -> dict:
    """Season-to-date splits; any split with < min_games is pooled with last season's."""
    cur = team_splits(current)
    prev = team_splits(previous) if previous is not None and not previous.empty else {}
    teams = set(cur) | set(prev)
    out = {}
    for t in teams:
        c = cur.get(t, {"home": Split(), "away": Split()})
        p = prev.get(t, {"home": Split(), "away": Split()})
        row = {}
        for side in ("home", "away"):
            s = c[side]
            row[side] = s + p[side] if s.games < min_games else s
            row[side + "_blended"] = s.games < min_games and p[side].games > 0
        row["overall"] = row["home"] + row["away"]
        out[t] = row
    return out


METHODS = {
    "switch": "Last season's table until round N, then this season only",
    "blend": "Blend each team with last season until it has N home/away games",
}


def _from_single(src: dict, teams: set, blended: bool) -> dict:
    out = {}
    for t in teams:
        x = src.get(t, {"home": Split(), "away": Split()})
        out[t] = {"home": x["home"], "away": x["away"], "overall": x["home"] + x["away"],
                  "home_blended": blended, "away_blended": blended}
    return out


def season_table(current: pd.DataFrame, previous: pd.DataFrame | None, round_no: float,
                 method: str = "switch", n: int = 6) -> dict:
    """The ATS splits used to rank a round.

    switch: rounds before `n` use last season's full table only ("blended" =
            True marks it as last season's); from round `n` on, this season only.
    blend:  per team, pool with last season until it has `n` home/away games.
    """
    previous = previous if previous is not None else current.iloc[0:0]
    if method == "blend":
        return blended_splits(current, previous, min_games=n)
    teams = set(team_splits(current)) | set(team_splits(previous))
    current_has_games = not current[current["ATS Result"].isin(["Home Cover", "Away Cover", "Push"])].empty
    if round_no < n or not current_has_games:   # no results yet this season -> last season's table
        return _from_single(team_splits(previous), teams, blended=True)
    return _from_single(team_splits(current), teams, blended=False)


def rank_fixtures(splits: dict, fixtures: list[dict]) -> pd.DataFrame:
    """Rank fixtures by split edge. Each fixture: home, away, home_line,
    and optional home_line_odds / away_line_odds. Games without a line are skipped."""
    rows = []
    for f in fixtures:
        home, away, line = f.get("home"), f.get("away"), f.get("home_line")
        if not home or not away or home == away or line is None or pd.isna(line):
            continue
        empty = {"home": Split(), "away": Split(), "overall": Split(),
                 "home_blended": False, "away_blended": False}
        h, a = splits.get(home, empty), splits.get(away, empty)   # new club: no record yet
        hs, as_ = h["home"].pct(), a["away"].pct()
        ho, ao = h["overall"].pct(), a["overall"].pct()
        if hs > as_:
            pick_home, edge = True, hs - as_
        elif as_ > hs:
            pick_home, edge = False, as_ - hs
        else:
            pick_home, edge = ho >= ao, abs(ho - ao)
        pick = home if pick_home else away
        line_for_pick = line if pick_home else -line
        odds = f.get("home_line_odds") if pick_home else f.get("away_line_odds")
        tier = "High" if edge >= 12 else "Medium" if edge >= 6 else "Low"
        rows.append({
            "Match": f"{home} vs {away}",
            "Home": home, "Away": away, "Home Line": line,
            "Pick": pick, "Opponent": away if pick_home else home, "Pick Is Home": pick_home,
            "Line For Pick": line_for_pick, "Line": f"{pick} {line_for_pick:+.1f}",
            "Odds": odds, "Edge (pts)": round(edge, 1), "Confidence": tier,
            "Home Split %": hs, "Away Split %": as_,
            "Home Split Record": h["home"].record(), "Away Split Record": a["away"].record(),
            "Home Blended": h["home_blended"], "Away Blended": a["away_blended"],
            "Home Overall %": ho, "Away Overall %": ao,
            "Game Id": f.get("game_id"),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("Edge (pts)", ascending=False, kind="stable").reset_index(drop=True)
    return out


def ats_table(splits: dict) -> pd.DataFrame:
    rows = []
    for t, s in splits.items():
        rows.append({
            "Team": t,
            "ATS": s["overall"].record(), "ATS %": s["overall"].pct(),
            "Home ATS": s["home"].record(), "Home ATS %": s["home"].pct(),
            "Away ATS": s["away"].record(), "Away ATS %": s["away"].pct(),
        })
    return pd.DataFrame(rows).sort_values("ATS %", ascending=False).reset_index(drop=True)


def grade_pick(home_line_for_pick: float, pick_margin: float) -> str:
    """'Win', 'Loss' or 'Push' given the pick's line and its winning margin."""
    diff = pick_margin + home_line_for_pick
    if abs(diff) < 1e-9:
        return "Push"
    return "Win" if diff > 0 else "Loss"
