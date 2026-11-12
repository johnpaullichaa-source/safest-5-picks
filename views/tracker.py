from __future__ import annotations

import pandas as pd
import streamlit as st

from safest5 import storage
from safest5.ats import grade_pick
from safest5.data import round_sort_key
from safest5.multis import settle_mix
from views.common import PICKS_FILE, SEASON, fmt_money, mix_editor, page_header, results

page_header(f"{SEASON} Tracker", "Your saved Safest 5, graded automatically as results land in nrl.xlsx, "
                                 "with running profit for singles and your chosen system.")

df = results()
if df is None:
    st.stop()
log = storage.load_json(PICKS_FILE)
if not log:
    st.info("No picks saved yet. Save a round's Safest 5 from This Round to start tracking.")
    st.stop()

season_games = df[df["Season"] == SEASON]
rows = []
for round_key, entries in log.items():
    for p in entries:
        g = season_games[(season_games["Home Team"] == p["home"]) & (season_games["Away Team"] == p["away"])]
        result = "Pending"
        if not g.empty:
            g = g.iloc[-1]
            margin = g["Margin"] if p["pick_is_home"] else -g["Margin"]
            line_for_pick = p["home_line"] if p["pick_is_home"] else -p["home_line"]
            result = grade_pick(line_for_pick, margin)
        rows.append({"Round": round_key, "Rank": p.get("rank"), "Pick": p["pick"], "Line": p["line_display"],
                     "Odds": p["odds"], "Confidence": p.get("confidence"), "Result": result})
graded = pd.DataFrame(rows)
graded["_o"] = graded["Round"].str.split(",").str[0].str.replace("Round ", "").apply(round_sort_key)
graded = graded.sort_values(["_o", "Rank"]).drop(columns="_o")

done = graded[graded["Result"] != "Pending"]
wins, losses = (done["Result"] == "Win").sum(), (done["Result"] == "Loss").sum()
st.subheader("Bet to track")
mix = mix_editor("trk", default_rows=[{"System": "Singles (5)", "Stake ($)": 50.0}])

settled = []
for round_key, g in graded.groupby("Round", sort=False):
    if (g["Result"] == "Pending").any():
        continue
    legs = list(zip(g.sort_values("Rank")["Odds"], g.sort_values("Rank")["Result"]))
    r = settle_mix(mix, legs) if mix else {"outlay": 0, "return": 0, "profit": 0, "landed": 0, "bets": 0}
    settled.append({"Round": round_key, "Winners": sum(1 for _, x in legs if x == "Win"),
                    "Bets": r["bets"], "Landed": r["landed"], "Outlay": r["outlay"],
                    "Return": r["return"], "Profit": r["profit"]})
settled = pd.DataFrame(settled)
if not settled.empty:
    settled = settled[settled["Bets"] > 0].reset_index(drop=True)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Picks covered", f"{wins}-{losses}", f"{wins / (wins + losses) * 100:.1f}%" if wins + losses else None)
if not settled.empty:
    prof, out = settled["Profit"].sum(), settled["Outlay"].sum()
    k2.metric("Profit", fmt_money(prof), f"{prof / out * 100:+.1f}% ROI" if out else None)
    k3.metric("Rounds settled", len(settled))
    k4.metric("Profitable rounds", f"{(settled['Profit'] > 0).sum()} of {len(settled)}")
    settled["Running profit"] = settled["Profit"].cumsum()
    st.line_chart(settled.set_index("Round")["Running profit"], height=260)
    st.dataframe(settled, hide_index=True, use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(format="$%.2f")
                                for c in ["Outlay", "Return", "Profit", "Running profit"]})

st.subheader("Every pick")
st.dataframe(graded, hide_index=True, use_container_width=True,
             column_config={"Odds": st.column_config.NumberColumn(format="$%.2f")})
st.caption("Picks are graded on the line you saved, not the closing line.")
