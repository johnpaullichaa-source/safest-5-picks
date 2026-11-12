# 🏉 Safest 5 Picks

A standalone Streamlit site for the weekly NRL **Safest 5 ATS** picks, a
**system multi simulator**, and a **backtest** of whether system multis on
those picks make money.

Data (`nrl.xlsx`, `NRL-2027-Fixtures.xlsx`) is read from the
[Nrl-match-data](https://github.com/johnpaullichaa-source/Nrl-match-data) repo,
so you keep updating one dataset. Saved picks go to `picks_log_2027.json` in
this repo.

## Pages

| Page | What it does |
|---|---|
| **This Round** | Pick a round, enter lines and prices, see games ranked by home/away ATS split edge. Save the top 5 to the tracker. |
| **Multi Simulator** | Put a system (2s/3s/4s from 5, full cover, custom) or a split of several (e.g. $25 on 3s + $25 on 4s) on five picks and see the return for every number of winners, plus every bet. |
| **Backtest** | Rebuilds the Safest 5 for every round since 2013 using only results known before each round, then settles singles, systems and your split. Shows ROI, running profit, season-by-season results, losing runs and drawdowns. |
| **2027 Tracker** | Grades saved picks as results land in `nrl.xlsx` and tracks profit for whichever bet you choose. |

## How the backtest works

- **Rounds** are betting weeks (Wednesday to Tuesday) within each season.
- **Picks** are ranked exactly like the live page: home team's Home ATS % vs away team's Away ATS %, overall ATS % as the tiebreak.
- **Early season:** a team's home (or away) split is pooled with last season's until it has 3 games this season (adjustable).
- **Lines:** closing line, or the opening line where there isn't one (most of 2024–25). **Prices:** matching line odds, or $1.90 if missing.
- **System multis:** each combination is its own multi; a pushed leg is void (odds 1.00); the stake is split evenly across the combinations. A system needing more picks than the round has isn't bet that round.

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

For local development without a token, put `nrl.xlsx` (and optionally
`NRL-2027-Fixtures.xlsx`) in a `data/` folder.

### Deploying on Streamlit Community Cloud

1. New app → this repo → main file `app.py`.
2. Under **Settings → Secrets**, paste the contents of `.streamlit/secrets.toml.example` with your token.
   The token needs **Contents: Read** on `Nrl-match-data` and **Contents: Read and write** on `safest-5-picks`.

Until `NRL-2027-Fixtures.xlsx` is in the NRL repo, This Round offers manual game entry.

## Tests

```bash
python -m pytest
```
