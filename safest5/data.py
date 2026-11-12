"""Load and normalise the NRL results workbook (nrl.xlsx) and fixture list.

Pure pandas: no Streamlit here, so it can be tested on its own.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

DEFAULT_LINE_ODDS = 1.90

TEAM_ALIASES = {
    "Cronulla Sharks": "Cronulla-Sutherland Sharks",
    "Manly Sea Eagles": "Manly-Warringah Sea Eagles",
    "North QLD Cowboys": "North Queensland Cowboys",
    "St George Dragons": "St. George Illawarra Dragons",
    "Canterbury Bulldogs": "Canterbury-Bankstown Bulldogs",
}

_NUMERIC = [
    "Home Score", "Away Score",
    "Home Line Open", "Home Line Close", "Away Line Open", "Away Line Close",
    "Home Line Odds Open", "Home Line Odds Close",
    "Away Line Odds Open", "Away Line Odds Close",
]


def _odds(series: pd.Series) -> pd.Series:
    """Treat zero / sub-1.01 prices as missing."""
    s = pd.to_numeric(series, errors="coerce")
    return s.where(s > 1.01)


def load_results(source) -> pd.DataFrame:
    """Read nrl.xlsx (path or bytes) into one row per completed game.

    Adds:
      Line / Line Source   closing home line, else opening line
      Home Line Price / Away Line Price   matching line odds, else $1.90
      ATS Margin / ATS Result             from the home side's perspective
      Season / Week                       Week = betting week (Wed-Tue)
    """
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    df = pd.read_excel(source, sheet_name="Data", header=1)
    df = df.dropna(subset=["Date", "Home Team", "Away Team", "Home Score", "Away Score"]).copy()
    for c in ("Home Team", "Away Team"):
        df[c] = df[c].astype(str).str.strip().replace(TEAM_ALIASES)
    df["Date"] = pd.to_datetime(df["Date"])
    for c in _NUMERIC:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = np.nan
    df = df.dropna(subset=["Home Score", "Away Score"]).copy()

    close, open_ = df["Home Line Close"], df["Home Line Open"]
    df["Line"] = close.fillna(open_)
    df["Line Source"] = np.where(close.notna(), "Close", np.where(open_.notna(), "Open", "None"))

    use_close = close.notna()
    h_close, h_open = _odds(df["Home Line Odds Close"]), _odds(df["Home Line Odds Open"])
    a_close, a_open = _odds(df["Away Line Odds Close"]), _odds(df["Away Line Odds Open"])
    df["Home Line Price"] = np.where(use_close, h_close, h_open)
    df["Away Line Price"] = np.where(use_close, a_close, a_open)
    df["Home Line Price"] = df["Home Line Price"].fillna(DEFAULT_LINE_ODDS)
    df["Away Line Price"] = df["Away Line Price"].fillna(DEFAULT_LINE_ODDS)

    df["Margin"] = df["Home Score"] - df["Away Score"]
    df["ATS Margin"] = df["Margin"] + df["Line"]
    df["ATS Result"] = np.select(
        [df["Line"].isna(), df["ATS Margin"] > 0, df["ATS Margin"] < 0],
        ["No Line", "Home Cover", "Away Cover"],
        default="Push",
    )
    df["Season"] = df["Date"].dt.year
    df["Finals"] = df.get("Play Off Game?", pd.Series(index=df.index, dtype=object)).astype(str).str.upper().eq("Y")

    # Betting week: Wednesday to Tuesday, numbered within each season.
    week_start = (df["Date"] - pd.to_timedelta((df["Date"].dt.dayofweek - 2) % 7, unit="D")).dt.normalize()
    df["Week Start"] = week_start
    df = df.sort_values(["Date"]).reset_index(drop=True)
    df["Week"] = df.groupby("Season")["Week Start"].rank(method="dense").astype(int)
    return df


def load_fixtures(source) -> pd.DataFrame:
    """Read a fixtures workbook (sheet 'Fixtures': Round Number, Location, Home Team, Away Team)."""
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    fx = pd.read_excel(source, sheet_name="Fixtures")
    fx = fx.dropna(subset=["Round Number", "Home Team", "Away Team"]).copy()
    for c in ("Home Team", "Away Team"):
        fx[c] = fx[c].astype(str).str.strip().replace(TEAM_ALIASES)
    fx["Round"] = fx["Round Number"].apply(clean_round_label)
    if "Location" not in fx.columns:
        fx["Location"] = ""
    fx["Round Order"] = fx["Round"].apply(round_sort_key)
    return fx.sort_values("Round Order", kind="stable").reset_index(drop=True)


def clean_round_label(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    fixes = {"finals weel 1": "Finals Week 1", "finals weel 2": "Finals Week 2",
             "finals weel 3": "Finals Week 3", "gf": "Grand Final", "grand final week": "Grand Final"}
    return fixes.get(s.lower(), s)


def round_sort_key(label: str) -> float:
    s = str(label).strip().lower()
    try:
        return float(s)
    except ValueError:
        pass
    if s.startswith("finals week"):
        try:
            return 100 + float(s.split()[-1])
        except ValueError:
            return 150
    if "grand" in s:
        return 200
    return 999
