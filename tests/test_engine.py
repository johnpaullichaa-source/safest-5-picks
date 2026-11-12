import pandas as pd
import pytest

from safest5.ats import blended_splits, rank_fixtures, season_table
from safest5.backtest import rebuild_picks
from safest5.multis import LOSS, PUSH, WIN, SystemMix, as_mix, payout_table, preset, settle, settle_mix


def legs(results, odds=1.90):
    return [(odds, r) for r in results]


def test_trebles_from_five_match_worked_example():
    s = preset("3s from 5")
    assert s.n_bets() == 10
    five = settle(s, legs([WIN] * 5), 50)
    four = settle(s, legs([WIN] * 4 + [LOSS]), 50)
    three = settle(s, legs([WIN] * 3 + [LOSS] * 2), 50)
    two = settle(s, legs([WIN] * 2 + [LOSS] * 3), 50)
    assert five["return"] == pytest.approx(342.95, abs=0.01)
    assert four["return"] == pytest.approx(137.18, abs=0.01) and four["landed"] == 4
    assert three["return"] == pytest.approx(34.30, abs=0.01) and three["landed"] == 1
    assert two["return"] == 0


def test_push_is_void_leg():
    s = preset("2s from 5")
    r = settle(s, legs([WIN, PUSH, LOSS, LOSS, LOSS]), 50)
    # Only the WIN+PUSH double lands, paying 1.90 on a $5 stake.
    assert r["landed"] == 1
    assert r["return"] == pytest.approx(5 * 1.90)


def test_full_cover_counts():
    assert preset("Full cover (26)").n_bets() == 26
    assert preset("Full cover + singles (31)").n_bets() == 31


def test_short_round_is_no_bet():
    r = settle(preset("3s from 5"), legs([WIN] * 4), 50)
    assert r["bets"] == 0 and r["profit"] == 0


def test_mix_adds_parts():
    mix = SystemMix("3s+4s", ((preset("3s from 5"), 25), (preset("4s from 5"), 25)))
    l = legs([WIN] * 4 + [LOSS])
    r = settle_mix(mix, l)
    a = settle(preset("3s from 5"), l, 25)
    b = settle(preset("4s from 5"), l, 25)
    assert r["outlay"] == 50
    assert r["return"] == pytest.approx(a["return"] + b["return"])


def test_payout_table_rows():
    rows = payout_table(preset("3s from 5"), [1.9] * 5, 50)
    assert [r["Picks that cover"] for r in rows] == [5, 4, 3, 2, 1, 0]
    assert rows[1]["Bets that land"] == 4


def _games():
    rows = []
    # Week 1: A home covers; Week 2: B (away) covers; Week 3: A vs B to rank.
    d = pd.Timestamp("2026-03-05")
    for wk, (h, a, line, hs, as_) in enumerate([("A", "B", -2.5, 20, 10), ("C", "B", -2.5, 10, 20), ("A", "C", -1.5, 10, 8)]):
        rows.append({"Home Team": h, "Away Team": a, "Line": line, "Home Score": hs, "Away Score": as_,
                     "Season": 2026, "Week": wk + 1, "Week Start": d + pd.Timedelta(days=7 * wk),
                     "Finals": False, "Line Source": "Close",
                     "Home Line Price": 1.9, "Away Line Price": 1.9})
    df = pd.DataFrame(rows)
    df["ATS Margin"] = df["Home Score"] - df["Away Score"] + df["Line"]
    df["ATS Result"] = df["ATS Margin"].apply(lambda m: "Home Cover" if m > 0 else "Away Cover" if m < 0 else "Push")
    return df


def test_no_lookahead():
    df = _games()
    picks = rebuild_picks(df, seasons=[2026], method="blend", n=0)
    # Week 1 has no prior results: both teams 0%, tiebreak picks home.
    w3 = picks[picks["Week"] == 3].iloc[0]
    # Before week 3, A is 1-0 at home and C is 0-0 away, so A is picked.
    assert w3["Pick"] == "A"
    assert w3["Result"] == WIN  # 10-8 with -1.5 covers


def test_blend_uses_last_season_when_thin():
    df = _games()
    prev = df.assign(Season=2025)
    splits = blended_splits(df.iloc[0:0], prev, min_games=3)
    assert splits["A"]["home"].covers == 2 and splits["A"]["home_blended"]


def test_short_round_adapts_when_asked():
    four = legs([WIN] * 4)
    assert settle(preset("3s from 5"), four, 50, adapt=True)["bets"] == 4      # 3s from 4
    assert settle(preset("5-leg multi"), four, 50, adapt=True)["bets"] == 1    # 4-leg multi
    assert settle(preset("Full cover (26)"), four, 50, adapt=True)["bets"] == 11  # 6+4+1
    assert settle(preset("4s from 5"), legs([WIN] * 2), 50, adapt=True)["bets"] == 0


def test_switch_rule_uses_last_season_then_this_season():
    df = _games()
    prev = df.assign(Season=2025, **{"ATS Result": "Away Cover"})
    early = season_table(df, prev, round_no=3, method="switch", n=6)
    late = season_table(df, prev, round_no=6, method="switch", n=6)
    assert early["A"]["home"].covers == 0 and early["A"]["home"].losses == 2   # 2025 only
    assert late["A"]["home"].covers == 2 and late["A"]["home"].losses == 0  # 2026 only
