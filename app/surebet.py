from __future__ import annotations

import re
import time
from itertools import product

from .models import Quote, Leg, Surebet


def norm(value: str) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip().lower())
    return value.replace("–", "-").replace("—", "-")


def effective_odds(q: Quote) -> float:
    # Polish betting-tax handling is intentionally NOT hard-coded here.
    # A quote is treated at face value; user can adjust BANKROLL but should
    # verify tax/account-specific rules before placing bets.
    return q.odds


def allocate(quotes: list[Quote], bankroll: float):
    if not quotes or any(q.odds <= 1 for q in quotes):
        return None

    inv_sum = sum(1.0 / effective_odds(q) for q in quotes)
    if inv_sum >= 1:
        return None

    payout = bankroll / inv_sum
    legs: list[Leg] = []

    for q in quotes:
        stake = payout / q.odds
        legs.append(
            Leg(
                selection=q.selection,
                bookmaker=q.bookmaker,
                odds=q.odds,
                stake=round(stake, 2),
                payout=round(payout, 2),
                bookmaker_url=q.bookmaker_url,
            )
        )

    # Make displayed stakes sum exactly to the requested bankroll.
    diff = round(bankroll - sum(x.stake for x in legs), 2)
    legs[-1].stake = round(legs[-1].stake + diff, 2)

    actual_payouts = [round(x.stake * x.odds, 2) for x in legs]
    guaranteed = min(actual_payouts)
    profit = round(guaranteed - bankroll, 2)
    return inv_sum, guaranteed, profit, legs


def _canonical_binary_group(labels: list[str]) -> list[str] | None:
    n = {norm(x): x for x in labels}

    yes = {"yes", "tak", "true", "over", "o", "home", "1"}
    no = {"no", "nie", "false", "under", "u", "away", "2"}

    if len(labels) == 2 and any(x in n for x in yes) and any(x in n for x in no):
        return labels

    # Common Polish/English two-way outcomes that are mutually exclusive.
    if len(labels) == 2:
        a, b = map(norm, labels)
        if (a.startswith("over ") and b.startswith("under ")) or (
            a.startswith("under ") and b.startswith("over ")
        ):
            return labels
        if ("yes" in a or "tak" in a) and ("no" in b or "nie" in b):
            return labels
        if ("no" in a or "nie" in a) and ("yes" in b or "tak" in b):
            return labels

    return None


def outcome_groups(quotes_by_selection: dict[str, list[Quote]], market: str) -> list[list[str]]:
    labels = list(quotes_by_selection)
    n = {norm(x): x for x in labels}
    groups: list[list[str]] = []

    # Exact 1X2 is the classic three-way mutually exclusive/exhaustive market.
    if all(x in n for x in ("1", "x", "2")):
        groups.append([n["1"], n["x"], n["2"]])

    # Two-way mutually exclusive markets.
    binary = _canonical_binary_group(labels)
    if binary:
        groups.append(binary)

    # Tennis/table-tennis/volleyball style winner markets often use two named sides.
    if len(labels) == 2:
        m = norm(market)
        if any(token in m for token in ("winner", "match winner", "zwycięzca", "wynik meczu")):
            groups.append(labels)

    # Do NOT automatically treat arbitrary two-outcome markets as arbs.
    # DNB, double chance and handicaps can contain pushes/overlap semantics.
    return groups


def detect(
    event: str,
    sport: str,
    market: str,
    quotes_by_selection: dict[str, list[Quote]],
    bankroll: float,
    min_profit_pct: float,
) -> list[Surebet]:
    groups = outcome_groups(quotes_by_selection, market)
    out: list[Surebet] = []
    seen: set[str] = set()

    # For each outcome choose every available bookmaker quote, then keep the
    # combination with the lowest implied probability. This preserves the
    # bookmaker alternatives instead of discarding them during parsing.
    for group in groups:
        choices = []
        for selection in group:
            qs = quotes_by_selection.get(selection, [])
            qs = [q for q in qs if q.odds > 1]
            if not qs:
                choices = []
                break
            choices.append(qs)

        if not choices:
            continue

        best = min(product(*choices), key=lambda combo: sum(1 / q.odds for q in combo))
        result = allocate(list(best), bankroll)
        if not result:
            continue

        _, payout, profit, legs = result
        pct = profit / bankroll * 100 if bankroll else 0
        if pct + 1e-9 < min_profit_pct:
            continue

        arb = Surebet(
            event=event,
            sport=sport,
            market=market,
            profit_pct=round(pct, 3),
            bankroll=bankroll,
            guaranteed_payout=payout,
            guaranteed_profit=profit,
            legs=legs,
            detected_at=time.time(),
        )
        if arb.key() not in seen:
            seen.add(arb.key())
            out.append(arb)

    return out
