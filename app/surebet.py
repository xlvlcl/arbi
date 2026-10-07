from __future__ import annotations

import re
import time

from .models import ArbLeg, Quote, Surebet


def normalize_name(value: str) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip().lower())
    return value.replace("–", "-").replace("—", "-").replace("↑", "").replace("↓", "").strip()


def _book_family(value: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "", normalize_name(value))
    aliases = {
        "efortuna": "fortuna",
        "totalbet": "totalbet",
        "totalbetpl": "totalbet",
        "etoto": "etoto",
        "betsport": "betsport",
    }
    return aliases.get(key, key)


MAX_REASONABLE_SUREBET_PROFIT_PCT = 40.0


def effective_odds(quote: Quote, payout_factor: float) -> float:
    return quote.odds * payout_factor


def _best_per_bookmaker(quotes: list[Quote]) -> list[Quote]:
    by_book: dict[str, Quote] = {}
    for quote in quotes:
        old = by_book.get(quote.bookmaker)
        if old is None or quote.odds > old.odds:
            by_book[quote.bookmaker] = quote
    return list(by_book.values())


def _extract_numbers(value: str) -> list[float]:
    out = []
    for raw in re.findall(r"(?<!\d)[+-]?\d+(?:[\.,]\d+)?", normalize_name(value)):
        try:
            out.append(float(raw.replace(",", ".")))
        except ValueError:
            pass
    return out


def _is_half_line(number: float) -> bool:
    # x.5 lines have no push in ordinary over/under and ordinary two-way handicap.
    return abs((number * 2) - round(number * 2)) < 1e-9 and int(round(number * 2)) % 2 == 1


def _same_total_line(market: str, labels: list[str]) -> bool:
    if len(labels) != 2:
        return False

    normalized = [normalize_name(x) for x in labels]
    joined = " | ".join(normalized)
    m = normalize_name(market)

    # Require clear complementary over/under wording either in outcomes or market.
    outcome_has_ou = (
        ("over" in joined and "under" in joined)
        or ("powyżej" in joined and "poniżej" in joined)
        or ("powyzej" in joined and "ponizej" in joined)
        or ("więcej" in joined and "mniej" in joined)
        or all(re.match(r"^[uo]\b", x) for x in normalized)
    )
    market_has_ou = any(token in m for token in ("u/o", "over/under", "over under", "total", "suma"))
    if not (outcome_has_ou or market_has_ou):
        return False

    label_nums = [_extract_numbers(x) for x in normalized]
    line = None
    if all(nums for nums in label_nums):
        if abs(label_nums[0][0] - label_nums[1][0]) > 1e-9:
            return False
        line = label_nums[0][0]
    else:
        market_nums = _extract_numbers(m)
        if market_nums:
            line = market_nums[-1]

    # Integer/quarter Asian totals can push / half-win and need different settlement math.
    return line is not None and _is_half_line(line)


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
    nums = _extract_numbers(m)
    return bool(nums) and _is_half_line(abs(nums[-1]))


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


def _is_htft(labels: list[str]) -> bool:
    if len(labels) != 9:
        return False
    normalized = {normalize_name(x).replace(" ", "") for x in labels}
    expected = {
        "1/1", "1/x", "1/2",
        "x/1", "x/x", "x/2",
        "2/1", "2/x", "2/2",
    }
    return normalized == expected


def _is_complete_set_score(labels: list[str]) -> bool:
    vals = {normalize_name(x).replace(" ", "") for x in labels}
    bo3 = {"2-0", "2-1", "0-2", "1-2"}
    bo5 = {"3-0", "3-1", "3-2", "0-3", "1-3", "2-3"}
    return vals == bo3 or vals == bo5


def _is_first_team_to_score(market: str, labels: list[str]) -> bool:
    m = normalize_name(market)
    if not any(token in m for token in (
        "kto strzeli pierwszy", "pierwsza drużyna strzeli",
        "pierwsza druzyna strzeli", "first team to score",
        "team to score first", "pierwszy gol - drużyna", "pierwszy gol - druzyna",
    )):
        return False
    if len(labels) != 3:
        return False
    joined = " | ".join(normalize_name(x) for x in labels)
    return any(token in joined for token in ("brak gola", "no goal", "none", "bez gola"))


def _is_complete_exact_score(market: str, labels: list[str]) -> bool:
    m = normalize_name(market)
    if not any(token in m for token in ("dokładny wynik", "dokladny wynik", "correct score")):
        return False
    if len(labels) < 5:
        return False
    joined = " | ".join(normalize_name(x) for x in labels)
    catch_all = any(token in joined for token in (
        "inny wynik", "inne", "pozostałe", "pozostale", "other", "any other",
    ))
    score_like = sum(bool(re.fullmatch(r"\d+\s*[:\-]\s*\d+", normalize_name(x))) for x in labels)
    return catch_all and score_like >= 3


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
    if _same_total_line(market, labels):
        return [labels]

    if _is_odd_even(labels):
        return [labels]

    if _is_half_handicap_market(market, labels):
        return [labels]

    if _is_two_way_winner(sport, market, labels):
        return [labels]

    if _is_complete_first_scorer(market, labels):
        return [labels]

    # Half-time / full-time: exactly nine mutually-exclusive combinations.
    if any(token in market_n for token in ("ht/ft", "ht-ft", "połowa/mecz", "polowa/mecz", "half time/full time")) and _is_htft(labels):
        return [labels]

    # Tennis/volleyball set score: only when the complete mathematically-known set is present.
    if any(token in market_n for token in ("wynik setów", "wynik setow", "set score", "dokładny wynik setów", "dokladny wynik setow")) and _is_complete_set_score(labels):
        return [labels]

    # First team to score, but only with the third "no goal" outcome.
    if _is_first_team_to_score(market, labels):
        return [labels]

    # Correct score is only safe when source includes an explicit catch-all "other" outcome.
    if _is_complete_exact_score(market, labels):
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
                        "source_name": alt.source_name,
                        "link_exact": bool(alt.link_exact),
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
        # A normal cross-book arbitrage must use at least two independent bookmakers.
        # If the raw best prices all happen to come from one book, try the next-best quote
        # on one leg before rejecting the market. This blocks same-page parser glitches while
        # still keeping legitimate cross-book opportunities that need the #2 price on a leg.
        if len({_book_family(q.bookmaker) for q in chosen if q.bookmaker}) < 2:
            rescue = None
            rescue_profit = float("-inf")
            for idx, selection in enumerate(group):
                for alt in alternatives.get(selection, [])[1:7]:
                    candidate = list(chosen)
                    candidate[idx] = alt
                    if len({_book_family(q.bookmaker) for q in candidate if q.bookmaker}) < 2:
                        continue
                    test = allocation(candidate, bankroll, factors, alternatives)
                    if not test:
                        continue
                    _, _, test_profit, _ = test
                    if test_profit > rescue_profit:
                        rescue_profit = test_profit
                        rescue = (candidate, test)
            if rescue is None:
                continue
            chosen, result = rescue
        else:
            result = allocation(chosen, bankroll, factors, alternatives)
            if not result:
                continue

        _, payout, profit, legs = result
        profit_pct = profit / bankroll * 100 if bankroll else 0.0
        if profit_pct + 1e-9 < min_profit_pct:
            continue
        # Extremely large "arbitrages" are overwhelmingly DOM/parser mistakes. Keep a
        # generous ceiling so real single-digit opportunities are unaffected.
        if profit_pct > MAX_REASONABLE_SUREBET_PROFIT_PCT:
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
