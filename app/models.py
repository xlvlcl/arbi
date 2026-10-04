from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class Quote:
    selection:str
    odds:float
    bookmaker:str
    observed_at:float
    source_url:str

@dataclass
class ArbLeg:
    selection:str
    bookmaker:str
    odds:float
    stake:float
    payout:float
    source_url:str

@dataclass
class Surebet:
    event:str
    sport:str
    market:str
    profit_pct:float
    bankroll:float
    guaranteed_payout:float
    guaranteed_profit:float
    legs:list[ArbLeg]
    detected_at:float
    source:str='DobryBuk public comparison'
    confidence:str='strict'

    def key(self):
        return '|'.join([self.sport,self.event,self.market]+[f'{x.selection}@{x.bookmaker}' for x in sorted(self.legs,key=lambda z:z.selection)])
    def to_dict(self):return asdict(self)
