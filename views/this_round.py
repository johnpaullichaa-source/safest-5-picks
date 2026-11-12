from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from safest5 import storage
from safest5.ats import ats_table, rank_fixtures, season_table
from safest5.data import DEFAULT_LINE_ODDS, round_sort_key

from views.common import PICKS_FILE, SEASON, fixtures, page_header, results, table_rule_controls


def _why(r: pd.Series, method: str) -> str:
    side = "home" if r["Pick Is Home"] else "away"
    pick_pct = r["Home Split %"] if r["Pick Is Home"] else r["Away Split %"]
    opp_pct = r["Away Split %"] if r["Pick Is Home"] else r["Home Split %"]
    pick_rec = r["Home Split Record"] if r["Pick Is Home"] else r["Away Split Record"]
    opp_rec = r["Away Split Record"] if r["Pick Is Home"] else r["Home Split Record"]
    opp_side = "away" if r["Pick Is Home"] else "home"
    blended = r["Home Blended"] if r["Pick Is Home"] else r["Away Blended"]
    note = (f" ({SEASON - 1} record)" if method == "switch" else " (includes last season)") if blended else ""
    return (f"{r['Pick']} cover {pick_pct:.0f}% at {side} ({pick_rec}){note}; "
            f"{r['Opponent']} cover {opp_pct:.0f}% {opp_side} ({opp_rec}).")


def render() -> None:  # noqa: C901
    page_header("This Round", f"{SEASON} games ranked by each side's home/away record against the line. "
                              "The top 5 are your Safest 5.")
    df = results()
    if df is None:
        return

    with st.sidebar:
        method, table_n = table_rule_controls(st.sidebar, "round")

    fx = fixtures()
    rounds = []
    if fx is not None and not fx.empty:
        rounds = sorted(fx["Round"].unique(), key=round_sort_key)
    c1, c2 = st.columns([1, 2])
    round_label = c1.selectbox("Round", rounds + ["Manual entry"], key="round_sel",
                               format_func=lambda r: r if r == "Manual entry" or not r.isdigit() else f"Round {r}")
    if fx is None:
        c2.info(f"NRL-{SEASON}-Fixtures.xlsx isn't in your NRL repo yet, so type the games in below.")

    if round_label == "Manual entry":
        base = pd.DataFrame([{"Home": "", "Away": ""} for _ in range(8)])
        round_no = c2.number_input("Round number", 1, 30, 1, key="manual_round_no")
        log_key = f"Round {int(round_no)}"
    else:
        rows = fx[fx["Round"] == round_label]
        base = rows[["Home Team", "Away Team"]].rename(columns={"Home Team": "Home", "Away Team": "Away"})
        log_key = f"Round {round_label}" if str(round_label).isdigit() else round_label
        round_no = int(round_label) if str(round_label).isdigit() else 99  # finals: this season
    full_key = f"{log_key}, {SEASON}"

    # Restore previously entered lines for this round.
    saved_inputs = st.session_state.setdefault("round_inputs", {}).get(full_key, {})
    base = base.reset_index(drop=True).copy()
    for col, k in (("Home line", "home_line"), ("Home line $", "home_odds"), ("Away line $", "away_odds")):
        base[col] = [saved_inputs.get(f"{h}|{a}", {}).get(k) for h, a in zip(base["Home"], base["Away"])]

    teams = sorted(set(df[df["Season"] >= SEASON - 1]["Home Team"]))
    st.subheader("Lines and prices")
    st.caption("Enter the home line (negative = home favourite). Prices default to $1.90 if left blank.")
    edited = st.data_editor(
        base, key=f"lines_{full_key}", hide_index=True, use_container_width=True,
        num_rows="dynamic" if round_label == "Manual entry" else "fixed",
        column_config={
            "Home": st.column_config.SelectboxColumn("Home", options=teams),
            "Away": st.column_config.SelectboxColumn("Away", options=teams),
            "Home line": st.column_config.NumberColumn("Home line", min_value=-50.0, max_value=50.0,
                                                       step=0.5, format="%+.1f"),
            "Home line $": st.column_config.NumberColumn("Home line $", min_value=1.01, step=0.01, format="$%.2f"),
            "Away line $": st.column_config.NumberColumn("Away line $", min_value=1.01, step=0.01, format="$%.2f"),
        },
    )
    st.session_state["round_inputs"][full_key] = {
        f"{r['Home']}|{r['Away']}": {"home_line": r["Home line"], "home_odds": r["Home line $"],
                                     "away_odds": r["Away line $"]}
        for _, r in edited.iterrows()
    }

    def _num(v):
        return None if v is None or pd.isna(v) else float(v)

    fixtures_in = [{
        "home": r["Home"], "away": r["Away"], "home_line": _num(r["Home line"]),
        "home_line_odds": _num(r["Home line $"]) or DEFAULT_LINE_ODDS,
        "away_line_odds": _num(r["Away line $"]) or DEFAULT_LINE_ODDS,
    } for _, r in edited.iterrows() if r["Home"] and r["Away"]]

    current = df[df["Season"] == SEASON]
    previous = df[df["Season"] == SEASON - 1]
    splits = season_table(current, previous, round_no, method, table_n)
    if method == "switch":
        src = f"{SEASON - 1} table" if round_no < table_n or current.empty else f"{SEASON} table"
    else:
        src = f"{SEASON}, blended with {SEASON - 1} while a team has fewer than {table_n} games"
    st.caption(f"Ranking with the **{src}**.")
    ranked = rank_fixtures(splits, fixtures_in)

    if ranked.empty:
        st.info("Add a home line for at least one game to rank this round.")
        with st.expander(f"ATS records used ({src})"):
            st.dataframe(ats_table(splits), hide_index=True, use_container_width=True)
        return

    top5 = ranked.head(5)
    st.session_state["current_top5"] = {
        "round": full_key,
        "labels": [f"{r['Line']}" for _, r in top5.iterrows()],
        "odds": [float(o) for o in top5["Odds"]],
    }

    st.subheader("Safest 5 this round")
    cols = st.columns(len(top5))
    for i, (col, (_, r)) in enumerate(zip(cols, top5.iterrows()), start=1):
        col.markdown(
            f"<div class='pick-card'><div class='rank'>#{i} · <span class='tier-{r['Confidence']}'>"
            f"{r['Confidence']}</span></div><div class='team'>{r['Pick']}</div>"
            f"<div class='line'>{r['Line For Pick']:+.1f} @ ${r['Odds']:.2f}</div>"
            f"<div class='meta'>vs {r['Opponent']} · edge {r['Edge (pts)']:.1f} pts</div></div>",
            unsafe_allow_html=True,
        )
    for i, (_, r) in enumerate(top5.iterrows(), start=1):
        st.caption(f"**#{i}** {_why(r, method)}")

    if len(top5) < 5:
        st.warning(f"Only {len(top5)} games have a line, so 5-pick systems will be skipped this round.")

    b1, b2 = st.columns([1, 3])
    if b1.button("Save Safest 5 to tracker", type="primary"):
        log = storage.load_json(PICKS_FILE)
        now = datetime.now(timezone.utc).isoformat()
        log[full_key] = [{
            "rank": i, "home": r["Home"], "away": r["Away"], "pick": r["Pick"],
            "pick_is_home": bool(r["Pick Is Home"]), "home_line": float(r["Home Line"]),
            "line_display": r["Line"], "odds": float(r["Odds"]), "edge": float(r["Edge (pts)"]),
            "confidence": r["Confidence"], "saved_at": now,
        } for i, (_, r) in enumerate(top5.iterrows(), start=1)]
        ok, msg = storage.save_json(PICKS_FILE, log, f"Save Safest 5 for {full_key}")
        (st.success if ok else st.error)(msg)
    b2.page_link("views/simulator.py", label="Try a system multi on these picks →", icon="🎯")

    st.subheader("All games")
    show = ranked[["Match", "Line", "Odds", "Edge (pts)", "Confidence",
                   "Home Split Record", "Home Split %", "Away Split Record", "Away Split %"]]
    st.dataframe(show, hide_index=True, use_container_width=True,
                 column_config={"Odds": st.column_config.NumberColumn(format="$%.2f")})

    with st.expander(f"ATS records used ({src})"):
        st.dataframe(ats_table(splits), hide_index=True, use_container_width=True)


render()
