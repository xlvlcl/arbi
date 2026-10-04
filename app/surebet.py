from __future__ import annotations

import re
import time

from .models import ArbLeg, Quote, Surebet


def normalize_name(value: str) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip().lower())
    return value.replace("–", "-").replace("—", "-").replace("↑", "").replace("↓", "").strip()


def effective_odds(quote: Quote, payout_factor: float) -> float:
    return quote.odds * payout_factor


def _best_per_bookmaker(quotes: list[Quote]) -> list[Quote]:
    by_book: dict[str, Quote] = {}
    for quote in quotes:
        old = by_book.get(quote.bookmaker)
        if old is None or quote.odds > old.odds:
            by_book[quote.bookmaker] = quote
    return list(by_book.values())


def _same_total_line(labels: list[str]) -> bool:
    if len(labels) != 2:
        return False
    normalized = [normalize_name(x) for x in labels]
    joined = " | ".join(normalized)
    if not any(token in joined for token in ("over", "under", "powyżej", "poniżej", "powyzej", "ponizej", "więcej", "mniej", " u ", " o ")):
        # Current source uses U 2.5 / O 2.5.
        if not all(re.match(r"^[uo]\s*\d", x) for x in normalized):
            return False
    nums = []
    for label in normalized:
        match = re.search(r"\d+(?:[\.,]\d+)?", label)
        nums.append(match.group(0).replace(",", ".") if match else None)
    return nums[0] is not None and nums[0] == nums[1]


def _is_yes_no(labels: list[str]) -> bool:
    if len(labels) != 2:
        return False
    values = {normalize_name(x) for x in labels}
    yes = {"tak", "yes", "y", "true"}
    no = {"nie", "no", "n", "false"}
    return bool(values & yes) and bool(values & no)


def _is_odd_even(labels: list[str]) -> bool:
    if len(labels) != 2:
        return False
    joined = " | ".join(normalize_name(x) for x in labels)
    return (
        ("odd" in joined and "even" in joined)
        or ("parzyst" in joined and "nieparzyst" in joined)
    )


def _is_half_handicap_market(market: str, labels: list[str]) -> bool:
    if len(labels) != 2:
        return False
    m = normalize_name(market)
    if "handicap" not in m and not re.search(r"\bh\s*[+-]", m):
        return False
    # Only half-point lines are treated as ordinary two-way outcomes.
    # Whole-number and quarter Asian lines can have push / half-win semantics that this calculator does not model.
    return bool(re.search(r"[+-]?\d+[\.,]5\b", m))


def _is_two_way_winner(sport: str, market: str, labels: list[str]) -> bool:
    if len(labels) != 2:
        return False
    m = normalize_name(market)
    if any(token in m for token in ("dnb", "draw no bet", "bez remisu", "remis nie gra", "double chance", "podwójna szansa", "podwojna szansa")):
        return False

    winner_tokens = (
        "winner",
        "match winner",
        "zwycięzca",
        "zwyciezca",
        "kto wygra",
        "wynik meczu",
        "wynik spotkania",
        "to win",
        "awans",
        "to qualify",
        "set winner",
        "game winner",
    )
    if any(token in m for token in winner_tokens):
        return True

    # DobryBuk may still call the main market 1x2 for sports where a draw is not a valid final result.
    drawless = {
        "tenis",
        "tenis stołowy",
        "siatkówka",
        "mma",
        "boks",
        "baseball",
    }
    if m in {"1x2", "1 x 2"} and normalize_name(sport) in drawless:
        vals = {normalize_name(x) for x in labels}
        return vals == {"1", "2"} or "x" not in vals
    return False


def _is_complete_first_scorer(market: str, labels: list[str]) -> bool:
    m = normalize_name(market)
    if not any(token in m for token in ("first scorer", "pierwszy strzelec", "pierwszy gol", "first goal")):
        return False
    if len(labels) < 3:
        return False
    joined = " | ".join(normalize_name(x) for x in labels)
    return any(token in joined for token in ("brak gola", "no goal", "none", "inne", "other"))


def outcome_groups(sport: str, market: str, labels: list[str]) -> list[list[str]]:
    """Return only outcome sets known to be mutually exclusive and exhaustive.

    This is intentionally conservative. Missing one outcome from a three-way market must never
    become a fake two-way surebet (the bug that produced the +88% examples).
    """
    if len(labels) < 2:
        return []

    # Dedupe exact labels but preserve source order.
    clean_labels: list[str] = []
    seen: set[str] = set()
    for label in labels:
        key = normalize_name(label)
        if not key or key in seen:
            continue
        seen.add(key)
        clean_labels.append(label)
    labels = clean_labels

    normalized = {normalize_name(x): x for x in labels}
    market_n = normalize_name(market)

    # Explicitly reject overlapping / push-prone groups.
    blocked = (
        "1x / x2 / 12",
        "1x/x2/12",
        "double chance",
        "podwójna szansa",
        "podwojna szansa",
        "dnb",
        "draw no bet",
        "remis nie gra",
        "bez remisu",
    )
    if any(token in market_n for token in blocked):
        return []

    # Football-style result: only valid if ALL 1/X/2 outcomes are present.
    if all(x in normalized for x in ("1", "x", "2")):
        return [[normalized["1"], normalized["x"], normalized["2"]]]
    if "x" in normalized and ("1" in normalized or "2" in normalized):
        # Incomplete 1X2 table: never reinterpret X+2 or 1+X as a binary market.
        return []

    # Explicit complementary propositions: scorer yes/no, BTTS yes/no, cards yes/no, etc.
    if _is_yes_no(labels):
        return [labels]

    # Totals on the same line (U/O 2.5, Over/Under 1.5, player shots O/U, etc.).
    if _same_total_line(labels):
        return [labels]

    if _is_odd_even(labels):
        return [labels]

    if _is_half_handicap_market(market, labels):
        return [labels]

    if _is_two_way_winner(sport, market, labels):
        return [labels]

    if _is_complete_first_scorer(market, labels):
        return [labels]

    return []


def allocation(
    quotes: list[Quote],
    bankroll: float,
    factors: dict[str, float],
    alternatives_by_selection: dict[str, list[Quote]] | None = None,
):
    if not quotes or bankroll <= 0 or any(q.odds <= 1.0 for q in quotes):
        return None

    denom = sum(
        1.0 / effective_odds(q, factors.get(q.bookmaker, 0.88))
        for q in quotes
    )
    if denom >= 1.0:
        return None

    target_payout = bankroll / denom
    legs: list[ArbLeg] = []
    for quote in quotes:
        factor = factors.get(quote.bookmaker, 0.88)
        eo = effective_odds(quote, factor)
        stake = target_payout / eo

        alternatives: list[dict] = []
        if alternatives_by_selection:
            candidates = alternatives_by_selection.get(quote.selection, [])
            for alt in candidates:
                if alt.bookmaker == quote.bookmaker:
                    continue
                alternatives.append(
                    {
                        "bookmaker": alt.bookmaker,
                        "odds": round(alt.odds, 2),
                        "bookmaker_url": alt.bookmaker_url,
                        "source_url": alt.source_url,
                    }
                )

        legs.append(
            ArbLeg(
                selection=quote.selection,
                bookmaker=quote.bookmaker,
                odds=quote.odds,
                stake=round(stake, 2),
                payout=round(target_payout, 2),
                source_url=quote.source_url,
                bookmaker_url=quote.bookmaker_url,
                alternatives=alternatives[:6],
            )
        )

    # Make displayed stakes add up exactly to bankroll.
    diff = round(bankroll - sum(x.stake for x in legs), 2)
    legs[-1].stake = round(legs[-1].stake + diff, 2)

    actual_payouts = []
    for leg, quote in zip(legs, quotes):
        factor = factors.get(quote.bookmaker, 0.88)
        actual_payouts.append(round(leg.stake * effective_odds(quote, factor), 2))

    guaranteed_payout = min(actual_payouts)
    guaranteed_profit = round(guaranteed_payout - bankroll, 2)
    return denom, guaranteed_payout, guaranteed_profit, legs


def detect(
    event: str,
    sport: str,
    market: str,
    quotes_by_selection: dict[str, list[Quote]],
    bankroll: float,
    factors: dict[str, float],
    min_profit_pct: float = 0.0,
    max_age: int = 180,
) -> list[Surebet]:
    now = time.time()
    best: dict[str, Quote] = {}
    alternatives: dict[str, list[Quote]] = {}

    for selection, quotes in quotes_by_selection.items():
        fresh = [
            q
            for q in _best_per_bookmaker(quotes)
            if now - q.observed_at <= max_age and q.odds > 1.0
        ]
        if not fresh:
            continue
        fresh.sort(
            key=lambda q: effective_odds(q, factors.get(q.bookmaker, 0.88)),
            reverse=True,
        )
        best[selection] = fresh[0]
        alternatives[selection] = fresh

    if not best:
        return []

    groups = outcome_groups(sport, market, list(best))
    results: list[Surebet] = []

    for group in groups:
        if any(selection not in best for selection in group):
            continue
        chosen = [best[selection] for selection in group]
        result = allocation(chosen, bankroll, factors, alternatives)
        if not result:
            continue

        _, payout, profit, legs = result
        profit_pct = profit / bankroll * 100 if bankroll else 0.0
        if profit_pct + 1e-9 < min_profit_pct:
            continue

        event_url = chosen[0].source_url if chosen else ""
        results.append(
            Surebet(
                event=event,
                sport=sport,
                market=market,
                profit_pct=round(profit_pct, 3),
                bankroll=bankroll,
                guaranteed_payout=round(payout, 2),
                guaranteed_profit=round(profit, 2),
                legs=legs,
                detected_at=now,
                event_url=event_url,
            )
        )

    return results
