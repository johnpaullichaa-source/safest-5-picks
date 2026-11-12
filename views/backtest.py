from __future__ import annotations

import pandas as pd
import streamlit as st

from safest5 import storage
from safest5.backtest import grade_saved_log, run_mixes, strike_rate, summarise
from safest5.multis import PRESETS, as_mix
from views.common import DEFAULT_OUTLAY, PICKS_FILE, fmt_money, legacy_log, mix_editor, page_header, results

page_header("Backtest", "How each system would have done on the Safest 5 picks you actually saved, "
                        "graded on the line saved with each pick.")

df = results()
if df is None:
    st.stop()

saved = {**legacy_log(), **storage.load_json(PICKS_FILE)}
picks = grade_saved_log(df, saved)
if not picks.empty:
    picks = picks[picks["Result"] != "Pending"].copy()
    picks["Finals"] = ~picks["Round"].str.startswith("Round")
if picks.empty:
    st.info("No saved rounds have results yet.")
    st.stop()

seasons = sorted(picks["Season"].unique())
with st.form("bt_settings"):
    c1, c2, c3 = st.columns([2, 1, 1])
    chosen_seasons = c1.multiselect("Seasons", seasons, default=seasons)
    outlay = c2.number_input("Outlay per round ($)", 5.0, 1000.0, DEFAULT_OUTLAY, step=5.0)
    include_finals = c3.checkbox("Include finals", value=True)
    adapt = c3.checkbox("Short rounds: play on picks available", value=True,
                        help="Finals weeks often have fewer than 5 picks. On: 3s from 5 becomes 3s from 4, "
                             "a 5-leg multi becomes a multi on every pick, and so on. Off: no bet that week.")
    chosen = st.multiselect("Systems (each staked the full outlay)", [s.name for s in PRESETS],
                            default=["Singles (5)", "2s from 5", "3s from 5", "4s from 5", "5-leg multi",
                                     "Full cover (26)"])
    st.markdown("**Split systems to compare** (optional). Each row is a part with its own stake.")
    mix = mix_editor("bt", default_rows=[{"System": "3s from 5", "Stake ($)": 25.0},
                                         {"System": "4s from 5", "Stake ($)": 25.0}])
    st.form_submit_button("Run backtest", type="primary")

picks = picks[picks["Season"].isin(chosen_seasons)]
if not include_finals:
    picks = picks[~picks["Finals"]]
if picks.empty:
    st.info("No saved rounds match those settings.")
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
k1.metric("Picks covered", f"{int(sr['Wins'])}-{int(sr['Losses'])}",
          f"{sr['Cover %']:.1f}% ({sr['Cover %'] - 100 / avg_odds:+.1f} vs break-even)")
k2.metric("Rounds", picks.groupby(["Season", "Round"]).ngroups)
k3.metric("Average price", f"${avg_odds:.2f}")
best = summary.sort_values("Profit", ascending=False).iloc[0]
k4.metric("Best system", best["System"], f"{best['ROI %']:+.1f}% ROI")
st.caption(f"At an average price of ${avg_odds:.2f}, picks must cover {100 / avg_odds:.1f}% to break even. "
           "Multis multiply the edge, good or bad. With only a few rounds logged, one round where "
           "all 5 cover can carry the whole result.")

# ---------- Summary ----------
st.subheader("Results by system")
money = {c: st.column_config.NumberColumn(c, format="$%.0f")
         for c in ["Outlay", "Return", "Profit", "Max drawdown", "Best round"]}
money.update({"ROI %": st.column_config.NumberColumn(format="%+.1f%%"),
              "Profitable rounds %": st.column_config.NumberColumn(format="%.0f%%")})
st.dataframe(summary.sort_values("Profit", ascending=False), hide_index=True,
             use_container_width=True, column_config=money)

# ---------- Round by round ----------
st.subheader("Round by round")
w = weekly[weekly["Bet"]].sort_values(["Season", "Week"]).copy()
multi_season = len(chosen_seasons) > 1
w["Label"] = w["Round"].astype(str) + ((", " + w["Season"].astype(str)) if multi_season else "")
order = list(dict.fromkeys(w["Label"]))
rr = w.pivot_table(index="Label", columns="System", values="Profit", aggfunc="sum").reindex(order)
covered = picks.groupby(["Season", "Round"])["Result"].apply(lambda r: f"{(r == 'Win').sum()}/{len(r)}")
firsts = w.drop_duplicates("Label")
rr.insert(0, "Covered", [covered.get((s, r), "") for s, r in zip(firsts["Season"], firsts["Round"])])
st.dataframe(rr, use_container_width=True,
             column_config={c: st.column_config.NumberColumn(c, format="$%.0f") for c in rr.columns[1:]})

st.subheader("Running profit")
w["Cumulative"] = w.groupby("System")["Profit"].cumsum()
chart = w.pivot_table(index="Label", columns="System", values="Cumulative", aggfunc="last").reindex(order).ffill()
chart.index = pd.CategoricalIndex(chart.index, categories=order, ordered=True)
st.line_chart(chart, height=360)

if multi_season:
    st.subheader("Profit by season")
    by_season = summarise(weekly, ["Season"]).pivot(index="Season", columns="System", values="Profit")
    by_season["Cover %"] = strike_rate(picks).set_index("Season")["Cover %"]
    st.dataframe(by_season.round(0), use_container_width=True)

with st.expander("How often each rank covers"):
    st.dataframe(strike_rate(picks, ["Rank"]).round(1), hide_index=True, use_container_width=True)

with st.expander("Every pick"):
    st.dataframe(picks.drop(columns=["Week"]), hide_index=True, use_container_width=True,
                 column_config={"Odds": st.column_config.NumberColumn(format="$%.2f")})

st.caption("Picks come from the 2026 log in your NRL app plus everything saved on this site. "
           f"Total staked in this view: {fmt_money(weekly['Outlay'].sum())}.")
