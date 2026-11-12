from __future__ import annotations

import pandas as pd
import streamlit as st

from safest5.multis import combo_list, mix_payout_table
from views.common import fmt_money, mix_editor, page_header

page_header("Multi Simulator", "Build a system multi (or a split of several) on five picks and see what it "
                               "returns for every number of winners.")

top5 = st.session_state.get("current_top5")
st.subheader("Picks")
if top5:
    st.caption(f"Loaded from This Round ({top5['round']}). Edit the prices here to play with them.")
    legs = pd.DataFrame({"Pick": top5["labels"], "Odds": top5["odds"]})
else:
    st.caption("Nothing on This Round yet, so here are five placeholder picks at $1.90. Edit them freely.")
    legs = pd.DataFrame({"Pick": [f"Pick {i}" for i in range(1, 6)], "Odds": [1.90] * 5})

legs = st.data_editor(
    legs, key="sim_legs", hide_index=True, use_container_width=True, num_rows="dynamic",
    column_config={"Odds": st.column_config.NumberColumn("Odds", min_value=1.01, step=0.01, format="$%.2f")},
).dropna()
legs = legs[legs["Pick"].astype(str).str.strip() != ""].head(5)
labels, odds = list(legs["Pick"].astype(str)), [float(o) for o in legs["Odds"]]

st.subheader("Your bet")
st.caption("Add a row per system. For a split, e.g. $25 on 3s and $25 on 4s, use two rows.")
mix = mix_editor("sim", default_rows=[{"System": "3s from 5", "Stake ($)": 25.0},
                                      {"System": "4s from 5", "Stake ($)": 25.0}])
if mix is None or not odds:
    st.info("Add at least one pick and one system with a stake.")
    st.stop()

skipped = [s.name for s, _ in mix.parts if not s.playable(len(odds))]
if skipped:
    st.warning(f"Not enough picks for: {', '.join(skipped)}. Those parts aren't placed.")

placed = [(s, o) for s, o in mix.parts if s.playable(len(odds))]
outlay = sum(o for _, o in placed)
bets = sum(s.n_bets(len(odds)) for s, _ in placed)
k1, k2, k3 = st.columns(3)
k1.metric("Total outlay", fmt_money(outlay))
k2.metric("Bets placed", bets)
full = mix_payout_table(mix, odds)[0]
k3.metric("If all cover", fmt_money(full["Max return"]), fmt_money(full["Max return"] - outlay))

st.subheader("What it returns")
table = pd.DataFrame(mix_payout_table(mix, odds))
uneven = len(set(odds)) > 1
cols = ["Picks that cover", "Bets that land", "Avg return", "Avg profit"] + (["Min return", "Max return"] if uneven else [])
money = {c: st.column_config.NumberColumn(c, format="$%.2f") for c in cols if "return" in c or "profit" in c}
st.dataframe(table[cols], hide_index=True, use_container_width=True, column_config=money)
if uneven:
    st.caption("Prices differ, so the return depends on which picks win. Min/avg/max cover every combination.")
breakeven = next((r["Picks that cover"] for r in reversed(table.to_dict("records")) if r["Avg profit"] > 0), None)
if breakeven is not None:
    st.caption(f"You need **{breakeven} of {len(odds)}** to cover to make a profit (on average).")

with st.expander(f"Every bet ({bets})"):
    rows = []
    for s, o in placed:
        for r in combo_list(s, labels, odds, o):
            rows.append({"System": s.name, **r})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={"Odds": st.column_config.NumberColumn(format="%.2f"),
                                "Stake": st.column_config.NumberColumn(format="$%.2f"),
                                "Pays": st.column_config.NumberColumn(format="$%.2f")})
