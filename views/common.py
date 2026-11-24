"""Shared loaders, styling and the system-mix editor used by several pages."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from safest5 import storage
from safest5.data import load_fixtures, load_results
from safest5.multis import SystemMix, systems_for

SEASON = 2027
FIXTURES_FILE = f"NRL-{SEASON}-Fixtures.xlsx"
PICKS_FILE = f"picks_log_{SEASON}.json"
DEFAULT_OUTLAY = 50.0
TABLE_METHOD_DEFAULT = "switch"
TABLE_N_DEFAULT = 6
# Clubs joining the comp that have no results in nrl.xlsx yet.
NEW_TEAMS = ["Perth Bears"]
LEGACY_LOG_FILE = "safest_picks_log.json"   # the old NRL app's 2026 log, in the data repo

CSS = """
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
.pick-card {border: 1px solid rgba(128,128,128,.25); border-radius: 12px; padding: .8rem .9rem;
            height: 100%; background: rgba(128,128,128,.04);}
.pick-card .rank {font-size: .75rem; opacity: .65; text-transform: uppercase; letter-spacing: .05em;}
.pick-card .team {font-weight: 700; font-size: 1.05rem; margin: .15rem 0;}
.pick-card .line {font-size: .95rem;}
.pick-card .meta {font-size: .8rem; opacity: .75; margin-top: .35rem;}
.tier-High {color: #1a7f37;} .tier-Medium {color: #b58100;} .tier-Low {color: #8c8c8c;}
</style>
"""


def page_header(title: str, subtitle: str) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(title)
    st.caption(subtitle)


@st.cache_data(show_spinner=False)
def _parse_results(raw: bytes) -> pd.DataFrame:
    return load_results(raw)


@st.cache_data(show_spinner=False)
def _parse_fixtures(raw: bytes) -> pd.DataFrame:
    return load_fixtures(raw)


def results() -> pd.DataFrame | None:
    raw, src = storage.read_data_file("nrl.xlsx")
    if raw is None:
        st.error(f"Couldn't load nrl.xlsx. {src}")
        st.info("Paste this into the app's Secrets (Manage app → ⋮ → Settings → Secrets), "
                "using the same token as your NRL app:")
        st.code('[github]\ntoken = "github_pat_..."', language="toml")
        return None
    return _parse_results(raw)


def fixtures() -> pd.DataFrame | None:
    raw, _ = storage.read_data_file(FIXTURES_FILE)
    return _parse_fixtures(raw) if raw else None


def table_rule_controls(container, key: str) -> tuple[str, int]:
    """Which ATS table ranks the picks. Shared default with the Backtest page."""
    from safest5.ats import METHODS
    method = container.selectbox(
        "ATS table rule", list(METHODS), key=f"{key}_method",
        index=list(METHODS).index(st.session_state.get("table_method", TABLE_METHOD_DEFAULT)),
        format_func=lambda m: METHODS[m])
    label = "Switch to this season from round" if method == "switch" else "Blend until N home/away games"
    n = container.number_input(label, 1, 12, int(st.session_state.get("table_n", TABLE_N_DEFAULT)),
                               key=f"{key}_n")
    st.session_state["table_method"], st.session_state["table_n"] = method, int(n)
    return method, int(n)


def legacy_log() -> dict:
    """The 2026 Safest 5 log saved by the old NRL app (read-only)."""
    import json
    raw, _ = storage.read_data_file(LEGACY_LOG_FILE)
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def fmt_money(x: float) -> str:
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


# ---------------------------------------------------------------------------
# System mix editor
# ---------------------------------------------------------------------------

def mix_editor(key: str, default_rows: list[dict] | None = None, label: str = "Your bet") -> SystemMix | None:
    """Edit a mix of systems, each with its own stake. Returns None if empty.
    “from 4” / “from 3” systems use the top 4 / top 3 ranked picks."""
    lookup = {s.name: s for n in (5, 4, 3) for s in systems_for(n)}
    options = list(lookup)
    default_rows = default_rows or [{"System": "3s from 5", "Stake ($)": 25.0},
                                    {"System": "4s from 5", "Stake ($)": 25.0}]
    edited = st.data_editor(
        pd.DataFrame(default_rows), key=f"{key}_editor", num_rows="dynamic", hide_index=True,
        use_container_width=True,
        column_config={
            "System": st.column_config.SelectboxColumn("System", options=options, required=True),
            "Stake ($)": st.column_config.NumberColumn("Stake ($)", min_value=0.0, step=5.0, format="$%.2f"),
        },
    )
    parts = []
    for _, r in edited.dropna(subset=["System"]).iterrows():
        stake = float(r.get("Stake ($)") or 0)
        if stake > 0 and r["System"] in lookup:
            parts.append((lookup[r["System"]], stake))
    if not parts:
        return None
    name = " + ".join(f"${o:g} {s.name}" for s, o in parts) if len(parts) > 1 else parts[0][0].name
    return SystemMix(name, tuple(parts))
