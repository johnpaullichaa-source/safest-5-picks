from __future__ import annotations

import pandas as pd
import streamlit as st

from safest5 import storage
from safest5.backtest import grade_saved_log, run_mixes
from views.common import PICKS_FILE, SEASON, fmt_money, mix_editor, page_header, results

page_header(f"{SEASON} Tracker", "Your saved Safest 5, graded automatically as results land in nrl.xlsx, "
                                 "with running profit for whichever bet you choose.")

df = results()
if df is None:
    st.stop()
log = storage.load_json(PICKS_FILE)
if not log:
    st.info("No picks saved yet. Save a round's Safest 5 from This Round to start tracking.")
    st.stop()

graded = grade_saved_log(df, log)
done = graded[graded["Result"] != "Pending"]
wins, losses = (done["Result"] == "Win").sum(), (done["Result"] == "Loss").sum()

st.subheader("Bet to track")
c1, c2 = st.columns([3, 1])
with c1:
    mix = mix_editor("trk", default_rows=[{"System": "3s from 5", "Stake ($)": 25.0},
                                          {"System": "4s from 5", "Stake ($)": 25.0}])
adapt = c2.checkbox("Short rounds: play on picks available", value=True, key="trk_adapt")

complete_rounds = graded.groupby(["Season", "Round"])["Result"].transform(lambda r: (r != "Pending").all())
settled_picks = graded[complete_rounds]
settled = pd.DataFrame()
if mix is not None and not settled_picks.empty:
    settled = run_mixes(settled_picks, [mix], adapt=adapt)
    settled = settled[settled["Bet"]].sort_values(["Season", "Week"]).reset_index(drop=True)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Picks covered", f"{wins}-{losses}", f"{wins / (wins + losses) * 100:.1f}%" if wins + losses else None)
if not settled.empty:
    prof, out = settled["Profit"].sum(), settled["Outlay"].sum()
    k2.metric("Profit", fmt_money(prof), f"{prof / out * 100:+.1f}% ROI" if out else None)
    k3.metric("Rounds bet", len(settled))
    k4.metric("Profitable rounds", f"{(settled['Profit'] > 0).sum()} of {len(settled)}")
    settled["Running profit"] = settled["Profit"].cumsum()
    chart = settled.set_index("Round")["Running profit"]
    chart.index = pd.CategoricalIndex(chart.index, categories=list(chart.index), ordered=True)
    st.line_chart(chart, height=260)
    st.dataframe(settled[["Round", "Picks", "Winners", "Bets", "Landed", "Outlay", "Return", "Profit",
                          "Running profit"]], hide_index=True, use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(format="$%.2f")
                                for c in ["Outlay", "Return", "Profit", "Running profit"]})
elif mix is None:
    st.info("Add a system with a stake to track profit.")

st.subheader("Every pick")
st.dataframe(graded.drop(columns=["Week"]), hide_index=True, use_container_width=True,
             column_config={"Odds": st.column_config.NumberColumn(format="$%.2f")})
st.caption("Picks are graded on the line you saved, not the closing line.")
