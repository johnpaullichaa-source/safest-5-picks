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
| **Backtest** | Settles singles, systems and your splits on the Safest 5 picks you actually saved (the 2026 log from the NRL app plus this site's log), graded on the line saved with each pick. Shows ROI, round-by-round profit, running profit, losing runs and drawdowns. |
| **2027 Tracker** | Grades saved picks as results land in `nrl.xlsx` and tracks profit for whichever bet you choose. |

## How the backtest works

- **Picks:** only saved Safest 5 picks: `safest_picks_log.json` in the NRL repo (Round 25, 2026 onwards) plus `picks_log_2027.json` here. Each is graded on the line saved with it.
- **System multis:** each combination is its own multi; a pushed leg is void (odds 1.00); the stake is split evenly across the combinations.
- **Short rounds (finals):** by default each system plays on the picks available (3s from 5 becomes 3s from 4, a 5-leg multi becomes a multi on every pick). Untick the option to skip those weeks instead.

## Which ATS table ranks the picks

Rounds 1–5 use last season's table; from Round 6, this season's results only (the switch round is a setting). Finals use this season.

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
