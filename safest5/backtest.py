"""Rebuild the Safest 5 for every past betting week and settle systems on it.

No look-ahead: picks for a week use only results from earlier weeks of that
season (blended with last season while a split is thin). Each pick is graded
against the line the data has for that game (closing, else opening) at the
matching line price (else $1.90).
"""
from __future__ import annotations

import pandas as pd

from .ats import blended_splits, rank_fixtures
from .multis import LOSS, PUSH, WIN, SystemMix, settle_mix


def rebuild_picks(results: pd.DataFrame, seasons: list[int] | None = None,
                  min_games: int = 3, top_n: int = 5) -> pd.DataFrame:
    """One row per pick: Season, Week, Rank, Pick, Line, Odds, Result."""
    df = results[results["Line"].notna()].copy()
    all_seasons = sorted(df["Season"].unique())
    seasons = seasons or all_seasons
    rows = []
    for season in seasons:
        season_df = df[df["Season"] == season]
        prev_df = df[df["Season"] == season - 1]
        for week in sorted(season_df["Week"].unique()):
            played = season_df[season_df["Week"] < week]
            games = season_df[season_df["Week"] == week]
            splits = blended_splits(played, prev_df, min_games=min_games)
            fixtures = [{
                "home": g["Home Team"], "away": g["Away Team"], "home_line": g["Line"],
                "home_line_odds": g["Home Line Price"], "away_line_odds": g["Away Line Price"],
                "game_id": idx,
            } for idx, g in games.iterrows()]
            ranked = rank_fixtures(splits, fixtures).head(top_n)
            for rank in range(1, len(ranked) + 1):
                g = games.loc[ranked.iloc[rank - 1]["Game Id"]]
                ats = g["ATS Result"]
                if ats == "Push":
                    result = PUSH
                elif (ats == "Home Cover") == bool(ranked.iloc[rank - 1]["Pick Is Home"]):
                    result = WIN
                else:
                    result = LOSS
                rows.append({
                    "Season": season, "Week": week, "Week Start": g["Week Start"],
                    "Finals": bool(g["Finals"]), "Rank": rank,
                    "Match": ranked.iloc[rank - 1]["Match"],
                    "Pick": ranked.iloc[rank - 1]["Pick"],
                    "Line": ranked.iloc[rank - 1]["Line"],
                    "Edge (pts)": ranked.iloc[rank - 1]["Edge (pts)"],
                    "Odds": float(ranked.iloc[rank - 1]["Odds"]),
                    "Line Source": g["Line Source"],
                    "Score": f"{int(g['Home Score'])}-{int(g['Away Score'])}",
                    "Result": result,
                })
    return pd.DataFrame(rows)


def run_mixes(picks: pd.DataFrame, mixes: list[SystemMix]) -> pd.DataFrame:
    """Settle every mix on every week. One row per (mix, week)."""
    rows = []
    if picks.empty:
        return pd.DataFrame(rows)
    for (season, week), wk in picks.groupby(["Season", "Week"], sort=True):
        wk = wk.sort_values("Rank")
        legs = list(zip(wk["Odds"], wk["Result"]))
        for mix in mixes:
            r = settle_mix(mix, legs)
            rows.append({
                "System": mix.name, "Season": season, "Week": week,
                "Week Start": wk["Week Start"].iloc[0],
                "Picks": len(legs), "Winners": sum(1 for _, x in legs if x == WIN),
                "Bet": r["bets"] > 0, **{k.title(): v for k, v in r.items()},
            })
    return pd.DataFrame(rows)


def _worst_losing_run(profits: list[float]) -> int:
    worst = run = 0
    for p in profits:
        run = run + 1 if p < 0 else 0
        worst = max(worst, run)
    return worst


def _max_drawdown(profits: list[float]) -> float:
    peak = cum = dd = 0.0
    for p in profits:
        cum += p
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return dd


def summarise(weekly: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    """Profit, ROI, strike rates and drawdowns per system (optionally per season)."""
    by = ["System"] + (by or [])
    rows = []
    bet = weekly[weekly["Bet"]]
    for key, g in bet.groupby(by, sort=False):
        key = key if isinstance(key, tuple) else (key,)
        g = g.sort_values(["Season", "Week"])
        outlay, profit = g["Outlay"].sum(), g["Profit"].sum()
        rows.append({
            **dict(zip(by, key)),
            "Rounds bet": len(g),
            "Outlay": outlay,
            "Return": g["Return"].sum(),
            "Profit": profit,
            "ROI %": profit / outlay * 100 if outlay else 0.0,
            "Profitable rounds %": (g["Profit"] > 0).mean() * 100,
            "Worst losing run": _worst_losing_run(list(g["Profit"])),
            "Max drawdown": _max_drawdown(list(g["Profit"])),
            "Best round": g["Profit"].max(),
        })
    return pd.DataFrame(rows)


def strike_rate(picks: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    by = by or ["Season"]
    d = picks.assign(W=picks["Result"].eq(WIN), L=picks["Result"].eq(LOSS), P=picks["Result"].eq(PUSH))
    g = d.groupby(by).agg(Picks=("Result", "size"), Wins=("W", "sum"), Losses=("L", "sum"),
                          Pushes=("P", "sum"), AvgOdds=("Odds", "mean")).reset_index()
    g["Cover %"] = g["Wins"] / (g["Wins"] + g["Losses"]) * 100
    return g.rename(columns={"AvgOdds": "Avg odds"})
