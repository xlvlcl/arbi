from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class Quote:
    selection: str
    odds: float
    bookmaker: str
    observed_at: float
    source_url: str
    bookmaker_url: str = ""


@dataclass
class Leg:
    selection: str
    bookmaker: str
    odds: float
    stake: float
    payout: float
    bookmaker_url: str = ""


@dataclass
class Surebet:
    event: str
    sport: str
    market: str
    profit_pct: float
    bankroll: float
    guaranteed_payout: float
    guaranteed_profit: float
    legs: list[Leg]
    detected_at: float
    source: str = "DobryBuk"

    def key(self) -> str:
        legs = "|".join(
            f"{x.selection.lower()}@{x.bookmaker.lower()}@{x.odds:.3f}"
            for x in sorted(self.legs, key=lambda x: (x.selection.lower(), x.bookmaker.lower()))
        )
        return f"{self.sport}|{self.event}|{self.market}|{legs}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
