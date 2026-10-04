from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Quote:
    selection: str
    odds: float
    bookmaker: str
    observed_at: float
    source_url: str
    bookmaker_url: str = ""
    source_name: str = ""
    link_exact: bool = False


@dataclass
class ArbLeg:
    selection: str
    bookmaker: str
    odds: float
    stake: float
    payout: float
    source_url: str
    bookmaker_url: str = ""
    source_name: str = ""
    link_exact: bool = False
    alternatives: list[dict] = field(default_factory=list)


@dataclass
class Surebet:
    event: str
    sport: str
    market: str
    profit_pct: float
    bankroll: float
    guaranteed_payout: float
    guaranteed_profit: float
    legs: list[ArbLeg]
    detected_at: float
    source: str = "Multi-source odds monitor"
    confidence: str = "strict"
    event_url: str = ""

    def key(self) -> str:
        legs = "|".join(
            f"{x.selection.strip().lower()}@{x.bookmaker.strip().lower()}"
            for x in sorted(self.legs, key=lambda z: z.selection.strip().lower())
        )
        return "|".join(
            [
                self.sport.strip().lower(),
                self.event.strip().lower(),
                self.market.strip().lower(),
                legs,
            ]
        )

    def to_dict(self) -> dict:
        return asdict(self)
