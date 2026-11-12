from __future__ import annotations

import pandas as pd
import streamlit as st

from safest5.backtest import rebuild_picks, run_mixes, strike_rate, summarise
from safest5.multis import PRESETS, as_mix
from views.common import DEFAULT_OUTLAY, MIN_GAMES_DEFAULT, fmt_money, mix_editor, page_header, results

page_header("Backtest", "Rebuilds the Safest 5 for every past round using only results known before it, "
                        "then settles each system on the real outcomes.")

df = results()
if df is None:
    st.stop()

seasons_avail = sorted(int(s) for s in df.loc[df["Line"].notna(), "Season"].unique())
lo, hi = seasons_avail[0], seasons_avail[-1]

with st.form("bt_settings"):
    c1, c2, c3 = st.columns([2, 1, 1])
    yr = c1.slider("Seasons", lo, hi, (lo, hi))
    outlay = c2.number_input("Outlay per round ($)", 5.0, 1000.0, DEFAULT_OUTLAY, step=5.0)
    min_games = c3.number_input("Blend until N games", 0, 8, MIN_GAMES_DEFAULT,
                                help="A team's home (or away) record is pooled with last season's until "
                                     "it has this many games this season.")
    c4, c5 = st.columns([2, 1])
    chosen = c4.multiselect("Systems (each staked the full outlay)", [s.name for s in PRESETS],
                            default=["Singles (5)", "2s from 5", "3s from 5", "4s from 5", "Full cover (26)"])
    include_finals = c5.checkbox("Include finals", value=True)
    st.markdown("**Split systems to compare** (optional). Each row is a part with its own stake.")
    mix = mix_editor("bt", default_rows=[{"System": "3s from 5", "Stake ($)": 25.0},
                                         {"System": "4s from 5", "Stake ($)": 25.0}])
    st.form_submit_button("Run backtest", type="primary")


@st.cache_data(show_spinner="Rebuilding every round's Safest 5…")
def _picks(data: pd.DataFrame, seasons: tuple[int, ...], min_games: int) -> pd.DataFrame:
    return rebuild_picks(data, seasons=list(seasons), min_games=min_games)


picks = _picks(df, tuple(range(yr[0], yr[1] + 1)), int(min_games))
if not include_finals:
    picks = picks[~picks["Finals"]]
if picks.empty:
    st.info("No rounds with lines in that range.")
    st.stop()

mixes = [as_mix(next(s for s in PRESETS if s.name == n), outlay) for n in chosen]
if mix is not None:
    mixes.append(mix)
if not mixes:
    st.info("Choose at least one system.")
    st.stop()

weekly = run_mixes(picks, mixes)
summary = summarise(weekly)

# ---------- Pick strike rate ----------
sr = strike_rate(picks.assign(All="All"), ["All"]).iloc[0]
avg_odds = picks["Odds"].mean()
k1, k2, k3, k4 = st.columns(4)
k1.metric("Pick cover rate", f"{sr['Cover %']:.1f}%", f"{sr['Cover %'] - 100 / avg_odds:+.1f} pts vs break-even")
k2.metric("Picks graded", f"{int(sr['Picks']):,}")
k3.metric("Average price", f"${avg_odds:.2f}")
best = summary.sort_values("Profit", ascending=False).iloc[0]
k4.metric("Best system", best["System"], f"{best['ROI %']:+.1f}% ROI")
st.caption(f"At an average price of ${avg_odds:.2f}, picks must cover {100 / avg_odds:.1f}% just to break even. "
           "Multis multiply the edge, good or bad.")

# ---------- Summary ----------
st.subheader("Results by system")
money = {c: st.column_config.NumberColumn(c, format="$%.0f")
         for c in ["Outlay", "Return", "Profit", "Max drawdown", "Best round"]}
money.update({"ROI %": st.column_config.NumberColumn(format="%+.1f%%"),
              "Profitable rounds %": st.column_config.NumberColumn(format="%.0f%%")})
st.dataframe(summary.sort_values("Profit", ascending=False), hide_index=True,
             use_container_width=True, column_config=money)

# ---------- Profit over time ----------
st.subheader("Running profit")
w = weekly[weekly["Bet"]].sort_values(["Season", "Week"]).copy()
w["Round"] = w["Season"].astype(str) + " W" + w["Week"].astype(str).str.zfill(2)
w["Cumulative"] = w.groupby("System")["Profit"].cumsum()
chart = w.pivot_table(index="Round", columns="System", values="Cumulative", aggfunc="last").sort_index().ffill()
st.line_chart(chart, height=380)

# ---------- By season ----------
st.subheader("Profit by season")
by_season = summarise(weekly, ["Season"]).pivot(index="Season", columns="System", values="Profit")
by_season["Pick cover %"] = strike_rate(picks).set_index("Season")["Cover %"]
st.dataframe(by_season.round(0), use_container_width=True,
             column_config={"Pick cover %": st.column_config.NumberColumn(format="%.1f%%")})
st.caption("Look for systems that are profitable in most seasons, not just one big year.")

# ---------- Detail ----------
with st.expander("How often the picks cover, by rank and season"):
    st.dataframe(strike_rate(picks, ["Rank"]).round(1), hide_index=True, use_container_width=True)
    st.dataframe(strike_rate(picks).round(1), hide_index=True, use_container_width=True)

with st.expander("Every rebuilt pick"):
    season_pick = st.selectbox("Season", sorted(picks["Season"].unique(), reverse=True), key="bt_detail_season")
    st.dataframe(picks[picks["Season"] == season_pick].drop(columns=["Week Start"]), hide_index=True,
                 use_container_width=True, column_config={"Odds": st.column_config.NumberColumn(format="$%.2f")})
    st.download_button("Download all picks (CSV)", picks.to_csv(index=False), "safest5_backtest_picks.csv")

st.caption("Lines: closing line where the data has one, otherwise opening line (most of 2024–25). "
           "Prices: the matching line odds, or $1.90 when missing. Rounds are betting weeks (Wed–Tue). "
           "A system that needs more picks than a week has (e.g. some finals) isn't bet that week. "
           f"Total staked in this view: {fmt_money(weekly['Outlay'].sum())}.")
