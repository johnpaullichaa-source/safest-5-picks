from __future__ import annotations

import pandas as pd
import streamlit as st

from safest5 import storage
from safest5.backtest import grade_saved_log, rebuild_picks, run_mixes, strike_rate, summarise
from safest5.multis import PRESETS, as_mix
from views.common import (DEFAULT_OUTLAY, PICKS_FILE, fmt_money, legacy_log, mix_editor, page_header,
                          results, table_rule_controls)

page_header("Backtest", "Rebuilds the Safest 5 for every past round using only results known before it, "
                        "then settles each system on the real outcomes.")

df = results()
if df is None:
    st.stop()

seasons_avail = sorted(int(s) for s in df.loc[df["Line"].notna(), "Season"].unique())
lo, hi = seasons_avail[0], seasons_avail[-1]

SOURCES = {"rebuilt": "Rebuilt picks: every round since 2013",
           "saved": "Saved picks only: the rounds you actually logged"}
source = st.radio("Picks to test", list(SOURCES), format_func=SOURCES.get, horizontal=True, key="bt_source")

with st.form("bt_settings"):
    c1, c2, c3 = st.columns([2, 1, 1])
    if source == "rebuilt":
        yr = c1.slider("Seasons", lo, hi, (lo, hi))
        method, table_n = table_rule_controls(c3, "bt")
    else:
        c1.caption("Uses the 2026 log from your NRL app plus everything saved on this site, "
                   "graded on the line saved with each pick.")
    outlay = c2.number_input("Outlay per round ($)", 5.0, 1000.0, DEFAULT_OUTLAY, step=5.0)
    adapt = c2.checkbox("Short rounds: play on picks available", value=True,
                        help="Finals weeks often have fewer than 5 picks. On: 3s from 5 becomes 3s from 4, "
                             "a 5-leg multi becomes a multi on every pick, and so on. Off: no bet that week.")
    c4, c5 = st.columns([2, 1])
    chosen = c4.multiselect("Systems (each staked the full outlay)", [s.name for s in PRESETS],
                            default=["Singles (5)", "2s from 5", "3s from 5", "4s from 5", "5-leg multi", "Full cover (26)"])
    include_finals = c5.checkbox("Include finals", value=True)
    st.markdown("**Split systems to compare** (optional). Each row is a part with its own stake.")
    mix = mix_editor("bt", default_rows=[{"System": "3s from 5", "Stake ($)": 25.0},
                                         {"System": "4s from 5", "Stake ($)": 25.0}])
    st.form_submit_button("Run backtest", type="primary")


@st.cache_data(show_spinner="Rebuilding every round's Safest 5…")
def _picks(data: pd.DataFrame, seasons: tuple[int, ...], method: str, n: int) -> pd.DataFrame:
    return rebuild_picks(data, seasons=list(seasons), method=method, n=n)


if source == "rebuilt":
    picks = _picks(df, tuple(range(yr[0], yr[1] + 1)), method, int(table_n))
else:
    saved = {**legacy_log(), **storage.load_json(PICKS_FILE)}
    picks = grade_saved_log(df, saved)
    if not picks.empty:
        picks = picks[picks["Result"] != "Pending"].copy()
        picks["Finals"] = ~picks["Round"].str.startswith("Round")
if not include_finals and not picks.empty:
    picks = picks[~picks["Finals"]]
if picks.empty:
    st.info("No saved rounds have results yet." if source == "saved" else "No rounds with lines in that range.")
    st.stop()

mixes = [as_mix(next(s for s in PRESETS if s.name == n), outlay) for n in chosen]
if mix is not None:
    mixes.append(mix)
if not mixes:
    st.info("Choose at least one system.")
    st.stop()

weekly = run_mixes(picks, mixes, adapt=adapt)
summary = summarise(weekly)
if summary.empty:
    st.info("None of these systems could be bet on the rounds selected.")
    st.stop()

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
w["Order"] = w["Season"] * 1000 + w["Week"]
w["Round"] = (w["Season"].astype(str) + " " + w["Round"].astype(str)) if source == "saved" else \
    (w["Season"].astype(str) + " W" + w["Week"].astype(str).str.zfill(2))
w["Cumulative"] = w.groupby("System")["Profit"].cumsum()
chart = w.pivot_table(index=["Order", "Round"], columns="System", values="Cumulative", aggfunc="last")
chart = chart.sort_index().ffill().droplevel("Order")
if source == "saved":
    chart.index = pd.CategoricalIndex(chart.index, categories=list(chart.index), ordered=True)
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

if source == "saved":
    with st.expander("Round by round"):
        rr = weekly[weekly["Bet"]].pivot_table(index=["Season", "Week", "Round"], columns="System",
                                               values="Profit", aggfunc="sum").droplevel("Week")
        st.dataframe(rr.round(2), use_container_width=True)

with st.expander("Every pick"):
    season_pick = st.selectbox("Season", sorted(picks["Season"].unique(), reverse=True), key="bt_detail_season")
    st.dataframe(picks[picks["Season"] == season_pick].drop(columns=["Week Start"], errors="ignore"), hide_index=True,
                 use_container_width=True, column_config={"Odds": st.column_config.NumberColumn(format="$%.2f")})
    st.download_button("Download all picks (CSV)", picks.to_csv(index=False), "safest5_backtest_picks.csv")

if source == "saved":
    st.caption("Small samples swing hard: one round where all 5 cover can carry a whole season. "
               "Compare with the rebuilt picks before trusting a result.")
st.caption("Lines: closing line where the data has one, otherwise opening line (most of 2024–25). "
           "Prices: the matching line odds, or $1.90 when missing. Rounds are betting weeks (Wed–Tue). "
           "Short rounds follow the option above. "
           f"Total staked in this view: {fmt_money(weekly['Outlay'].sum())}.")
