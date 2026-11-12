"""Safest 5 Picks: weekly NRL ATS picks, a system multi simulator and a backtest."""
import streamlit as st

from safest5 import storage

st.set_page_config(page_title="Safest 5 Picks", page_icon="🏉", layout="wide")

pages = [
    st.Page("views/this_round.py", title="This Round", icon="🏉", default=True),
    st.Page("views/simulator.py", title="Multi Simulator", icon="🎯", url_path="simulator"),
    st.Page("views/backtest.py", title="Backtest", icon="📈", url_path="backtest"),
    st.Page("views/tracker.py", title="2027 Tracker", icon="📋", url_path="tracker"),
]

with st.sidebar:
    st.markdown("### Safest 5 Picks")
    st.caption(storage.status_line())
    if st.button("Reload data from NRL repo"):
        storage.refresh_data()
        st.rerun()

st.navigation(pages).run()
