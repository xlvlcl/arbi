from __future__ import annotations

import hashlib
import time

from app.merge import event_key, market_key
from app.surebet import outcome_groups


def _factor(book: str, factors: dict[str, float]) -> float:
    return float(factors.get(book, 0.88))


def _fresh_best(markets_quotes: dict, max_age_seconds: int) -> dict[str, dict]:
    now = time.time()
    out: dict[str, dict] = {}
    for selection, quotes in (markets_quotes or {}).items():
        best = None
        best_effective = 0.0
        for q in quotes:
            book = str(q.get("bookmaker", "")).strip()
            odds = float(q.get("odds", 0) or 0)
            observed = float(q.get("observed_at", 0) or 0)
            if not book or odds <= 1.0:
                continue
            if observed and now - observed > max_age_seconds:
                continue
            # effective value is filled later because factor map is external
            if best is None or odds > float(best.get("odds", 0) or 0):
                best = q
        if best:
            out[str(selection)] = best
    return out


def detect_near_arbs(
    markets: list[dict],
    payout_factors: dict[str, float],
    *,
    max_gap_pct: float = 1.50,
    max_age_seconds: int = 300,
) -> list[dict]:
    """Find markets that are close to becoming a strict surebet.

    gap_pct is the extra effective price improvement needed (approximately)
    before inverse-sum crosses below 1. These are WATCH signals, not bets.
    """
    results: list[dict] = []

    for market in markets:
        quotes = _fresh_best(market.get("quotes") or {}, max_age_seconds)
        if len(quotes) < 2:
            continue

        groups = outcome_groups(
            str(market.get("sport", "")),
            str(market.get("market", "")),
            list(quotes),
        )
        if not groups:
            continue

        for group in groups:
            legs = []
            inv_sum = 0.0
            books = set()
            complete = True

            for selection in group:
                candidates = []
                for q in (market.get("quotes") or {}).get(selection, []):
                    book = str(q.get("bookmaker", "")).strip()
                    odds = float(q.get("odds", 0) or 0)
                    observed = float(q.get("observed_at", market.get("observed_at", 0)) or 0)
                    if not book or odds <= 1.0:
                        continue
                    if observed and time.time() - observed > max_age_seconds:
                        continue
                    effective = odds * _factor(book, payout_factors)
                    if effective <= 1.0:
                        continue
                    candidates.append((effective, q))

                if not candidates:
                    complete = False
                    break

                effective, best = max(candidates, key=lambda x: x[0])
                inv_sum += 1.0 / effective
                books.add(str(best.get("bookmaker", "")))
                legs.append(
                    {
                        "selection": str(selection),
                        "bookmaker": str(best.get("bookmaker", "")),
                        "odds": round(float(best.get("odds", 0) or 0), 3),
                        "effective_odds": round(effective, 3),
                        "bookmaker_url": best.get("bookmaker_url", "")
                        or best.get("source_url", ""),
                        "source_url": best.get("source_url", ""),
                    }
                )

            if not complete or inv_sum <= 1.0:
                continue

            gap_pct = (inv_sum - 1.0) * 100.0
            if gap_pct > max_gap_pct:
                continue

            event = str(market.get("event", ""))
            sport = str(market.get("sport", ""))
            market_name = str(market.get("market", ""))
            raw_key = "|".join(
                [event_key(event), sport.lower(), market_key(market_name)]
            )
            key = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:20]
            source_count = len(set(market.get("source_names") or []))
            diversity = len(books)

            # Higher = more urgent. Gap dominates; book/source diversity breaks ties.
            score = max(0.0, (max_gap_pct - gap_pct) / max_gap_pct) * 100.0
            score += min(20.0, diversity * 2.0)
            score += min(10.0, source_count * 2.0)

            results.append(
                {
                    "key": key,
                    "event": event,
                    "sport": sport,
                    "market": market_name,
                    "event_url": market.get("event_url", ""),
                    "gap_pct": round(gap_pct, 4),
                    "inverse_sum": round(inv_sum, 6),
                    "score": round(score, 2),
                    "bookmakers": diversity,
                    "sources": market.get("source_names", []),
                    "legs": legs,
                }
            )

    unique = {}
    for item in results:
        old = unique.get(item["key"])
        if old is None or item["gap_pct"] < old["gap_pct"]:
            unique[item["key"]] = item

    return sorted(
        unique.values(),
        key=lambda x: (x["gap_pct"], -x["bookmakers"], -x["score"]),
    )


def scan_quality(markets: list[dict]) -> dict:
    events = set()
    books = set()
    offers = 0
    selections = 0
    source_names = set()

    for market in markets:
        ekey = event_key(str(market.get("event", "")))
        if ekey:
            events.add(ekey)
        source_names.update(str(x) for x in (market.get("source_names") or []))
        for _, quotes in (market.get("quotes") or {}).items():
            if quotes:
                selections += 1
            for q in quotes:
                book = str(q.get("bookmaker", "")).strip()
                if book:
                    books.add(book)
                    offers += 1

    return {
        "events": len(events),
        "markets": len(markets),
        "selections": selections,
        "offers": offers,
        "bookmakers": len(books),
        "sources": len(source_names),
        "offers_per_market": round(offers / max(1, len(markets)), 2),
        "markets_per_event": round(len(markets) / max(1, len(events)), 2),
    }
