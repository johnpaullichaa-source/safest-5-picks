"""System multi maths.

A system is a set of leg sizes applied to n picks, e.g. "3s from 5" = every
3-leg combination of 5 picks (10 trebles). Each combination is its own multi:
it pays stake x product of its legs' odds if every leg wins. A pushed leg is
void (odds 1.00); a losing leg kills that combination. The round outlay is
split evenly across every combination.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import comb, prod

WIN, LOSS, PUSH = "Win", "Loss", "Push"


@dataclass(frozen=True)
class System:
    name: str
    sizes: tuple[int, ...]   # leg sizes, e.g. (3,) or (2, 3, 4, 5)
    picks: int = 5           # how many of the top picks it uses

    def n_bets(self, n_picks: int | None = None) -> int:
        n = min(self.picks, n_picks if n_picks is not None else self.picks)
        return sum(comb(n, k) for k in self.sizes if k <= n)

    def playable(self, n_picks: int, adapt: bool = False) -> bool:
        """Without adapt: only if we have every pick the system is built on.
        With adapt: if any of its leg sizes fit the picks available."""
        if n_picks >= self.picks:
            return True
        return adapt and bool(self.sizes_for(n_picks)) and n_picks > 0

    def sizes_for(self, n: int) -> tuple[int, ...]:
        """Leg sizes to use when a round only has n picks (e.g. finals).
        The all-legs size (e.g. 5 in a 5-leg multi or full cover) becomes n;
        sizes bigger than n are dropped. 3s from 5 with 4 picks -> 3s from 4;
        full cover with 4 picks -> 2s, 3s and the 4-leg; 4s with 2 picks -> no bet."""
        if n >= self.picks:
            return self.sizes
        mapped = {n if k == self.picks else k for k in self.sizes}
        return tuple(sorted(k for k in mapped if 1 <= k <= n))


PRESETS: list[System] = [
    System("Singles (5)", (1,)),
    System("2s from 5", (2,)),
    System("3s from 5", (3,)),
    System("4s from 5", (4,)),
    System("5-leg multi", (5,)),
    System("Full cover (26)", (2, 3, 4, 5)),
    System("Full cover + singles (31)", (1, 2, 3, 4, 5)),
]


def preset(name: str) -> System:
    return next(s for s in PRESETS if s.name == name)


def settle(system: System, legs: list[tuple[float, str]], outlay: float, adapt: bool = False) -> dict:
    """Settle one round.

    legs: [(odds, result)] for the top picks in rank order; only the first
    `system.picks` are used. With adapt=True a round with fewer picks (finals)
    plays the system on the picks available (see System.sizes_for); otherwise
    it isn't bet. Returns bets, stake per bet, return, profit, combos landed.
    """
    legs = legs[: system.picks]
    n = len(legs)
    if not system.playable(n, adapt):
        return {"bets": 0, "stake": 0.0, "outlay": 0.0, "return": 0.0, "profit": 0.0, "landed": 0}
    combos = [c for k in system.sizes_for(n) for c in combinations(range(n), k)]
    stake = outlay / len(combos)
    ret, landed = 0.0, 0
    for c in combos:
        if any(legs[i][1] == LOSS for i in c):
            continue
        landed += 1
        ret += stake * prod(1.0 if legs[i][1] == PUSH else legs[i][0] for i in c)
    return {"bets": len(combos), "stake": stake, "outlay": outlay,
            "return": ret, "profit": ret - outlay, "landed": landed}


@dataclass(frozen=True)
class SystemMix:
    """Several systems played together, each with its own outlay,
    e.g. $25 on 3s from 5 + $25 on 4s from 5."""
    name: str
    parts: tuple[tuple[System, float], ...]

    @property
    def outlay(self) -> float:
        return sum(o for _, o in self.parts)

    @property
    def picks(self) -> int:
        return max(s.picks for s, _ in self.parts)

    def n_bets(self) -> int:
        return sum(s.n_bets() for s, _ in self.parts)


def settle_mix(mix: SystemMix, legs: list[tuple[float, str]], adapt: bool = False) -> dict:
    """Settle each part with its own outlay and add them up. A part that can't
    be played this round (too few picks) is skipped, not counted as a loss."""
    total = {"bets": 0, "outlay": 0.0, "return": 0.0, "profit": 0.0, "landed": 0}
    for system, outlay in mix.parts:
        r = settle(system, legs, outlay, adapt)
        for k in total:
            total[k] += r[k]
    return total


def as_mix(system: System, outlay: float) -> SystemMix:
    return SystemMix(system.name, ((system, outlay),))


def mix_payout_table(mix: SystemMix, odds: list[float]) -> list[dict]:
    """Like payout_table, for a split of systems."""
    n = min(len(odds), mix.picks)
    odds = odds[:n]
    rows = []
    for w in range(n, -1, -1):
        returns, landed = [], []
        for winners in combinations(range(n), w):
            ws = set(winners)
            legs = [(o, WIN if i in ws else LOSS) for i, o in enumerate(odds)]
            r = settle_mix(mix, legs)
            returns.append(r["return"])
            landed.append(r["landed"])
        outlay = sum(o for s, o in mix.parts if s.playable(n))
        rows.append({
            "Picks that cover": w,
            "Bets that land": round(sum(landed) / len(landed), 1),
            "Min return": min(returns),
            "Avg return": sum(returns) / len(returns),
            "Max return": max(returns),
            "Avg profit": sum(returns) / len(returns) - outlay,
        })
    return rows


def payout_table(system: System, odds: list[float], outlay: float) -> list[dict]:
    """Return for each number of winning picks (no pushes).

    With uneven odds the result depends on *which* picks win, so we report the
    lowest, average and highest return across every way that many could win.
    """
    odds = odds[: system.picks]
    n = len(odds)
    rows = []
    for w in range(n, -1, -1):
        returns = []
        for winners in combinations(range(n), w):
            ws = set(winners)
            legs = [(o, WIN if i in ws else LOSS) for i, o in enumerate(odds)]
            returns.append(settle(system, legs, outlay)["return"])
        landed = sum(comb(w, k) for k in system.sizes if k <= w)
        rows.append({
            "Picks that cover": w,
            "Bets that land": landed,
            "Min return": min(returns),
            "Avg return": sum(returns) / len(returns),
            "Max return": max(returns),
            "Avg profit": sum(returns) / len(returns) - outlay,
        })
    return rows


def combo_list(system: System, labels: list[str], odds: list[float], outlay: float) -> list[dict]:
    labels, odds = labels[: system.picks], odds[: system.picks]
    n = len(labels)
    combos = [c for k in system.sizes if k <= n for c in combinations(range(n), k)]
    if not combos:
        return []
    stake = outlay / len(combos)
    return [{
        "Legs": len(c),
        "Selections": " + ".join(labels[i] for i in c),
        "Odds": prod(odds[i] for i in c),
        "Stake": stake,
        "Pays": stake * prod(odds[i] for i in c),
    } for c in combos]
