from __future__ import annotations

import pandas as pd
import streamlit as st

from safest5.multis import SystemMix, combo_list, mix_payout_table, systems_for
from views.common import fmt_money, page_header

page_header("Multi Simulator", "Choose your legs and odds, add one or more systems with a stake, "
                               "and see what every result pays.")

# ---------------------------------------------------------------- 1. Legs
st.subheader("1. Your legs")
top5 = st.session_state.get("current_top5")
st.session_state.setdefault("sim_n", 5)
st.session_state.setdefault("sim_load", 0)
c1, c2 = st.columns([1, 2])
if top5 and c2.button(f"Load Safest 5 from This Round ({top5['round']})"):
    st.session_state["sim_n"] = len(top5["labels"])
    st.session_state["sim_last_legs"] = pd.DataFrame({"Selection": top5["labels"], "Odds": top5["odds"]})
    st.session_state["sim_load"] += 1

n = int(c1.number_input("Number of legs", min_value=2, max_value=10, step=1, key="sim_n"))

# Each (legs, load) combination gets its own table with a fixed starting copy,
# carrying over whatever was typed in the previous one.
legs_key = f"sim_legs_{n}_{st.session_state['sim_load']}"
if legs_key + "_base" not in st.session_state:
    last = st.session_state.get("sim_last_legs")
    if last is None:
        last = pd.DataFrame({"Selection": [f"Leg {i}" for i in range(1, 6)], "Odds": [1.90] * 5})
    extra = pd.DataFrame({"Selection": [f"Leg {i}" for i in range(len(last) + 1, n + 1)],
                          "Odds": [1.90] * max(0, n - len(last))})
    st.session_state[legs_key + "_base"] = pd.concat([last, extra], ignore_index=True).head(n)

legs = st.data_editor(
    st.session_state[legs_key + "_base"], key=legs_key, hide_index=True, use_container_width=True,
    num_rows="fixed",
    column_config={
        "Selection": st.column_config.TextColumn("Selection", width="large"),
        "Odds": st.column_config.NumberColumn("Odds", min_value=1.01, step=0.05, format="$%.2f", required=True),
    },
)
st.session_state["sim_last_legs"] = legs
legs = legs.fillna({"Odds": 1.90})
labels = [str(x) if pd.notna(x) and str(x).strip() else f"Leg {i}" for i, x in enumerate(legs["Selection"], 1)]
odds = [float(o) for o in legs["Odds"]]

# ---------------------------------------------------------------- 2. Systems
st.subheader("2. Your system(s)")
st.caption("Add a row for each system. For a split, e.g. $25 on 3s and $25 on 4s, add two rows. "
           "“Total” spreads the stake evenly over that system's bets; “Per bet” puts it on each bet.")
options = systems_for(n)
by_label = {f"{s.name} · {s.n_bets()} bet{'s' if s.n_bets() != 1 else ''}": s for s in options}
labels_list = list(by_label)

def _default_rows() -> pd.DataFrame:
    want = [f"3s from {n}", f"4s from {n}"] if n >= 5 else [options[1].name]
    rows = [{"System": lbl, "Stake ($)": 25.0, "Stake is": "Total"}
            for lbl, s in by_label.items() if s.name in want]
    return pd.DataFrame(rows or [{"System": labels_list[0], "Stake ($)": 50.0, "Stake is": "Total"}])

sys_key = f"sim_systems_{n}"   # options depend on the number of legs
st.session_state.setdefault(sys_key + "_base", _default_rows())
systems = st.data_editor(
    st.session_state[sys_key + "_base"], key=sys_key, hide_index=True,
    use_container_width=True, num_rows="dynamic",
    column_config={
        "System": st.column_config.SelectboxColumn("System", options=labels_list, required=True, width="large"),
        "Stake ($)": st.column_config.NumberColumn("Stake ($)", min_value=0.0, step=5.0, format="$%.2f",
                                                   required=True),
        "Stake is": st.column_config.SelectboxColumn("Stake is", options=["Total", "Per bet"], required=True),
    },
)

parts = []
for _, r in systems.dropna(subset=["System"]).iterrows():
    s = by_label.get(r["System"])
    stake = float(r["Stake ($)"]) if pd.notna(r["Stake ($)"]) else 0.0
    if s is None or stake <= 0:
        continue
    outlay = stake * s.n_bets() if r.get("Stake is") == "Per bet" else stake
    parts.append((s, outlay))

if not parts:
    st.info("Add at least one system with a stake.")
    st.stop()

mix = SystemMix(" + ".join(f"{fmt_money(o)} {s.name}" for s, o in parts), tuple(parts))

# ---------------------------------------------------------------- 3. Payouts
st.subheader("3. Payouts")
outlay = mix.outlay
bets = mix.n_bets()
table = pd.DataFrame(mix_payout_table(mix, odds))
best = table.iloc[0]

k1, k2, k3 = st.columns(3)
k1.metric("Total outlay", fmt_money(outlay))
k2.metric("Bets", bets)
k3.metric(f"If all {n} win", fmt_money(best["Max return"]), fmt_money(best["Max return"] - outlay))

st.markdown(f"**{mix.name}**")
uneven = len(set(odds)) > 1
table["Profit"] = table["Avg return"] - outlay
show = table.rename(columns={"Picks that cover": "Legs that win", "Avg return": "Return"})
cols = ["Legs that win", "Bets that land", "Return", "Profit"]
if uneven:
    show = show.rename(columns={"Min return": "Lowest", "Max return": "Highest"})
    cols += ["Lowest", "Highest"]
st.dataframe(show[cols], hide_index=True, use_container_width=True,
             column_config={c: st.column_config.NumberColumn(c, format="$%.2f")
                            for c in ["Return", "Profit", "Lowest", "Highest"]})
if uneven:
    st.caption("Your odds differ, so the return depends on which legs win. “Return” is the average "
               "over every way that many legs could win; “Lowest”/“Highest” show the range.")
need = next((int(r["Picks that cover"]) for r in reversed(table.to_dict("records")) if r["Profit"] > 0), None)
if need is not None:
    st.success(f"You need **{need} of {n}** legs to win to make a profit"
               + (" (on average)." if uneven else "."))
else:
    st.warning("This bet doesn't make a profit even if every leg wins.")

# ---------------------------------------------------------------- Every bet
with st.expander(f"See every bet ({bets})"):
    rows = []
    for s, o in parts:
        for r in combo_list(s, labels, odds, o):
            rows.append({"System": s.name, **r})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={"Odds": st.column_config.NumberColumn(format="%.2f"),
                                "Stake": st.column_config.NumberColumn(format="$%.2f"),
                                "Pays": st.column_config.NumberColumn(format="$%.2f")})
