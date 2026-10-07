from __future__ import annotations

"""Server-side odds feeds used as reliable alternatives to browser scraping.

The adapters in this module only use documented HTTP APIs. They deliberately do not try
CAPTCHA solving, Cloudflare bypassing, proxy rotation, fingerprint spoofing, or other
anti-bot evasion. If a public bookmaker page blocks a GitHub runner, the scanner can use
one of these feeds instead.
"""

import asyncio
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urljoin

import httpx


BOOKMAKER_ALIASES = {
    "betclic": "Betclic",
    "betclic pl": "Betclic",
    "betclic.pl": "Betclic",
    "efortuna": "Fortuna",
    "efortuna pl": "Fortuna",
    "fortuna": "Fortuna",
    "fortuna pl": "Fortuna",
    "sts": "STS",
    "sts pl": "STS",
    "sts.pl": "STS",
    "superbet": "Superbet",
    "superbet pl": "Superbet",
    "superbet.pl": "Superbet",
    "betfan": "Betfan",
    "betfan pl": "Betfan",
    "betfan.pl": "Betfan",
    "lv bet": "LVBet",
    "lvbet": "LVBet",
    "lvbet pl": "LVBet",
    "lvbet.pl": "LVBet",
    "etoto": "ETOTO",
    "e toto": "ETOTO",
    "forbet": "Forbet",
    "forbet pl": "Forbet",
    "iforbet": "Forbet",
    "fuksiarz": "Fuksiarz",
    "lebull": "LeBull",
    "betters": "Betters",
    "totalbet": "TotalBet",
    "total bet": "TotalBet",
    "comeon": "ComeOn",
    "admiralbet": "AdmiralBet",
    "betsport": "BetSport",
    "pzbuk": "PZBuk",
    "traf": "TRAF",
    "wett arena": "Wett Arena",
    "wettarena": "Wett Arena",
}

BOOKMAKER_HOME = {
    "Betclic": "https://www.betclic.pl/",
    "Fortuna": "https://www.efortuna.pl/",
    "STS": "https://www.sts.pl/",
    "Superbet": "https://superbet.pl/",
    "Betfan": "https://betfan.pl/",
    "LVBet": "https://lvbet.pl/",
    "ETOTO": "https://www.etoto.pl/",
    "Forbet": "https://www.iforbet.pl/",
    "Fuksiarz": "https://fuksiarz.pl/",
    "LeBull": "https://lebull.pl/",
    "Betters": "https://betters.pl/",
    "TotalBet": "https://totalbet.pl/",
    "ComeOn": "https://comeon.pl/",
    "AdmiralBet": "https://admiralbet.pl/",
    "BetSport": "https://betsport.pl/",
    "PZBuk": "https://www.pzbuk.pl/",
    "TRAF": "https://trafonline.pl/",
    "Wett Arena": "https://wettarena.pl/",
}

ODDS_API_IO_WANTED_BOOKS = (
    "Betclic PL",
    "eFortuna PL",
    "STS PL",
    "Superbet",
    "Betfan PL",
    "LVbet PL",
    "ComeOn",
)

ODDS_API_IO_DEFAULT_SPORTS = (
    "football",
    "basketball",
    "tennis",
    "ice-hockey",
    "volleyball",
    "handball",
)

SPORT_PL = {
    "football": "Piłka nożna",
    "soccer": "Piłka nożna",
    "basketball": "Koszykówka",
    "tennis": "Tenis",
    "ice hockey": "Hokej",
    "ice-hockey": "Hokej",
    "hockey": "Hokej",
    "volleyball": "Siatkówka",
    "handball": "Piłka ręczna",
    "mma": "MMA",
    "boxing": "Boks",
    "baseball": "Baseball",
    "american football": "Futbol amerykański",
    "table tennis": "Tenis stołowy",
    "darts": "Dart",
    "rugby": "Rugby",
    "badminton": "Badminton",
    "cricket": "Krykiet",
    "esports": "Esport",
}


def _canonical_book(value: str) -> str:
    raw = re.sub(r"\s+", " ", str(value or "").strip())
    low = raw.lower()
    return BOOKMAKER_ALIASES.get(low, raw)


def _sport_name(value) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("slug") or ""
    raw = str(value or "").strip()
    return SPORT_PL.get(raw.lower(), raw or "Inne")


def _float(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out <= 1.0 or out > 1000.0:
        return None
    return out


def _timestamp(value, *, fallback: float | None = None) -> float:
    if isinstance(value, (int, float)):
        val = float(value)
        if val > 10_000_000_000:
            val /= 1000.0
        return val
    if isinstance(value, str) and value.strip():
        raw = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(raw).timestamp()
        except ValueError:
            pass
    return float(time.time() if fallback is None else fallback)


def _row_key(event_id: str, market: str) -> tuple[str, str]:
    return str(event_id), re.sub(r"\s+", " ", str(market or "").strip().lower())


def _append_quote(rows: dict, *, event_id: str, event: str, sport: str, market: str,
                  selection: str, odds, bookmaker: str, observed_at: float,
                  source_url: str, bookmaker_url: str, source_name: str,
                  link_exact: bool = False) -> None:
    odd = _float(odds)
    if not odd or not event or not market or not selection or not bookmaker:
        return
    key = _row_key(event_id, market)
    row = rows.setdefault(
        key,
        {
            "event": event,
            "sport": sport or "Inne",
            "market": market,
            "quotes": {},
            "observed_at": observed_at,
            "source_url": source_url,
            "event_url": source_url,
            "source_name": source_name,
        },
    )
    row["observed_at"] = max(float(row.get("observed_at", 0) or 0), float(observed_at))
    row["quotes"].setdefault(selection, []).append(
        {
            "selection": selection,
            "odds": odd,
            "bookmaker": bookmaker,
            "observed_at": observed_at,
            "source_url": source_url,
            "bookmaker_url": bookmaker_url,
            "source_name": source_name,
            "link_exact": bool(link_exact),
        }
    )


def _arbiscan_market_name(key: str, outcomes: list[dict]) -> tuple[str, dict[str, str]]:
    raw = str(key or "").strip()
    low = raw.lower()
    names = [str(x.get("name", "") or "").strip() for x in outcomes]
    labels: dict[str, str] = {}

    if low == "h2h":
        normalized = {x.lower() for x in names}
        has_draw = "draw" in normalized or "remis" in normalized or "x" in normalized
        market = "1X2" if has_draw else "Winner"
        for name in names:
            n = name.lower()
            if n in {"home", "1", "gospodarz"}:
                labels[name] = "1"
            elif n in {"away", "2", "gość", "gosc"}:
                labels[name] = "2"
            elif n in {"draw", "remis", "x"}:
                labels[name] = "X"
            else:
                labels[name] = name
        return market, labels

    # ArbiScan documents full keys such as Total|2.5 and Total Corners|9.5.
    market = raw.replace("|", " ").strip() or "Rynek"
    for name in names:
        n = name.lower()
        if n in {"yes", "tak"}:
            labels[name] = "Yes"
        elif n in {"no", "nie"}:
            labels[name] = "No"
        else:
            labels[name] = name
    return market, labels


def _arbiscan_deep_link(book: str, bookmaker: dict) -> tuple[str, bool]:
    home = BOOKMAKER_HOME.get(book, "")
    path = str(bookmaker.get("bookmaker_event_path", "") or "").strip()
    if home and path:
        try:
            # Path comes from the feed for that bookmaker. urljoin keeps the known HTTPS origin.
            return urljoin(home, path), True
        except Exception:
            pass
    return home, False


def parse_arbiscan_events(events: list[dict], *, fetched_at: float | None = None) -> list[dict]:
    """Convert documented ArbiScan event objects into the scanner's market rows."""
    rows: dict[tuple[str, str], dict] = {}
    fetched_at = float(fetched_at or time.time())
    for event_obj in events or []:
        if not isinstance(event_obj, dict):
            continue
        event_id = str(event_obj.get("id") or event_obj.get("canonical_id") or "").strip()
        home = str(event_obj.get("home_team", "") or "").strip()
        away = str(event_obj.get("away_team", "") or "").strip()
        if not event_id or not home or not away:
            continue
        event_name = f"{home} vs {away}"
        sport = _sport_name(event_obj.get("sport"))
        source_url = f"https://api.arbiscan.pl/v1/events/{quote(event_id, safe='')}"

        for bookmaker in event_obj.get("bookmakers") or []:
            if not isinstance(bookmaker, dict):
                continue
            book = _canonical_book(bookmaker.get("key", ""))
            if not book:
                continue
            deep_link, link_exact = _arbiscan_deep_link(book, bookmaker)
            for market_obj in bookmaker.get("markets") or []:
                if not isinstance(market_obj, dict):
                    continue
                outcomes = [x for x in (market_obj.get("outcomes") or []) if isinstance(x, dict)]
                if len(outcomes) < 2:
                    continue
                market, labels = _arbiscan_market_name(str(market_obj.get("key", "")), outcomes)
                for outcome in outcomes:
                    original_name = str(outcome.get("name", "") or "").strip()
                    selection = labels.get(original_name, original_name)
                    observed_at = _timestamp(
                        outcome.get("last_update")
                        or market_obj.get("last_update")
                        or bookmaker.get("last_update"),
                        fallback=fetched_at,
                    )
                    _append_quote(
                        rows,
                        event_id=event_id,
                        event=event_name,
                        sport=sport,
                        market=market,
                        selection=selection,
                        odds=outcome.get("price"),
                        bookmaker=book,
                        observed_at=observed_at,
                        source_url=source_url,
                        bookmaker_url=deep_link,
                        source_name="ArbiScan API",
                        link_exact=link_exact,
                    )
    return list(rows.values())


async def scan_arbiscan(*, api_key: str, timeout: float = 18.0, max_pages: int = 1,
                        max_age_seconds: int = 300) -> tuple[list[dict], list[str], dict]:
    if not api_key:
        return [], [], {"configured": False, "provider": "ArbiScan API", "markets": 0, "events": 0}

    errors: list[str] = []
    events: list[dict] = []
    requests = 0
    cursor = ""
    quota = {}
    headers = {"X-API-Key": api_key, "Accept": "application/json"}
    params = {
        "max_age_seconds": min(900, max(60, int(max_age_seconds))),
        "limit": 500,
    }

    async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(timeout)) as client:
        for page in range(max(1, int(max_pages))):
            try:
                request_params = {"limit": 500}
                if cursor:
                    request_params["cursor"] = cursor
                else:
                    request_params.update(params)
                response = await client.get("https://api.arbiscan.pl/v1/odds", params=request_params)
                requests += 1
                response.raise_for_status()
                body = response.json()
                quota = body.get("quota") or quota
                page_events = body.get("events") or []
                if isinstance(page_events, list):
                    events.extend(x for x in page_events if isinstance(x, dict))
                if not body.get("has_more"):
                    break
                cursor = str(body.get("next_cursor") or "")
                if not cursor:
                    break
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                detail = ""
                try:
                    data = exc.response.json()
                    detail = str(data.get("code") or data.get("error") or "")
                except Exception:
                    pass
                errors.append(f"HTTP {status}{(': ' + detail) if detail else ''}")
                break
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                break

    rows = parse_arbiscan_events(events, fetched_at=time.time())
    event_ids = {str(e.get("id") or e.get("canonical_id") or "") for e in events if isinstance(e, dict)}
    return rows, errors, {
        "configured": True,
        "provider": "ArbiScan API",
        "ok": bool(rows) and not errors,
        "events": len(event_ids - {""}),
        "markets": len(rows),
        "requests": requests,
        "quota": quota,
    }


async def confirm_arbiscan(*, api_key: str, event_ids: set[str], timeout: float = 14.0,
                           concurrency: int = 4) -> tuple[list[dict], list[str], dict]:
    if not api_key or not event_ids:
        return [], [], {"configured": bool(api_key), "provider": "ArbiScan API confirm", "markets": 0}
    errors: list[str] = []
    events: list[dict] = []
    sem = asyncio.Semaphore(max(1, min(8, int(concurrency))))
    headers = {"X-API-Key": api_key, "Accept": "application/json"}

    async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(timeout)) as client:
        async def one(event_id: str):
            async with sem:
                try:
                    url = f"https://api.arbiscan.pl/v1/events/{quote(event_id, safe='')}"
                    response = await client.get(url)
                    response.raise_for_status()
                    body = response.json()
                    return body if isinstance(body, dict) else None, None
                except Exception as exc:
                    return None, f"{event_id}: {type(exc).__name__}: {exc}"

        results = await asyncio.gather(*(one(x) for x in sorted(event_ids)[:32]))
    for event_obj, error in results:
        if error:
            errors.append(error)
        if event_obj:
            events.append(event_obj)
    rows = parse_arbiscan_events(events, fetched_at=time.time())
    return rows, errors, {
        "configured": True,
        "provider": "ArbiScan API confirm",
        "events": len(events),
        "markets": len(rows),
        "requests": len(results),
        "ok": bool(rows),
    }


def _odds_api_market_name(name: str, odds_rows: list[dict]) -> str:
    low = str(name or "").strip().lower()
    if low in {"moneyline", "ml", "match winner", "winner"}:
        has_draw = any(_float(x.get("draw")) for x in odds_rows if isinstance(x, dict))
        return "1X2" if has_draw else "Winner"
    if low in {"both teams to score", "btts", "both teams score"}:
        return "Both Teams To Score"
    return str(name or "Rynek").strip() or "Rynek"


def parse_odds_api_io_events(items: list[dict], *, fetched_at: float | None = None) -> list[dict]:
    """Parse documented Odds-API.io v3 event/odds objects.

    The provider's market updatedAt is a *price-change* time, not necessarily the time the
    feed was checked. For our freshness gate we therefore use fetched_at as observed_at;
    the actual provider timestamp is not discarded by the feed itself, but it must not make
    an unchanged-yet-current price look stale after five minutes.
    """
    rows: dict[tuple[str, str], dict] = {}
    fetched_at = float(fetched_at or time.time())
    for item in items or []:
        if not isinstance(item, dict):
            continue
        event_id = str(item.get("id", "") or "").strip()
        home = str(item.get("home", "") or "").strip()
        away = str(item.get("away", "") or "").strip()
        if not event_id or not home or not away:
            continue
        event = f"{home} vs {away}"
        sport = _sport_name(item.get("sport"))
        urls = item.get("urls") if isinstance(item.get("urls"), dict) else {}
        source_url = f"https://api.odds-api.io/v3/odds?eventId={quote(event_id, safe='')}"
        bookmakers = item.get("bookmakers") or {}
        if not isinstance(bookmakers, dict):
            continue

        for raw_book, markets in bookmakers.items():
            book = _canonical_book(raw_book)
            if not book or not isinstance(markets, list):
                continue
            deep_link = str(urls.get(raw_book, "") or BOOKMAKER_HOME.get(book, ""))
            link_exact = bool(urls.get(raw_book))
            for market_obj in markets:
                if not isinstance(market_obj, dict):
                    continue
                name = str(market_obj.get("name", "") or "").strip()
                odds_rows = [x for x in (market_obj.get("odds") or []) if isinstance(x, dict)]
                if not odds_rows:
                    continue
                low = name.lower()

                if low in {"moneyline", "ml", "match winner", "winner"}:
                    market = _odds_api_market_name(name, odds_rows)
                    for odd_row in odds_rows:
                        for field, label in (("home", "1"), ("draw", "X"), ("away", "2")):
                            _append_quote(
                                rows,
                                event_id=event_id,
                                event=event,
                                sport=sport,
                                market=market,
                                selection=label,
                                odds=odd_row.get(field),
                                bookmaker=book,
                                observed_at=fetched_at,
                                source_url=source_url,
                                bookmaker_url=deep_link,
                                source_name="Odds-API.io",
                                link_exact=link_exact,
                            )
                    continue

                if low in {"totals", "total"}:
                    for odd_row in odds_rows:
                        hdp = odd_row.get("hdp")
                        if hdp is None:
                            continue
                        market = f"Total {hdp}"
                        for field, label in (("over", "Over"), ("under", "Under")):
                            _append_quote(
                                rows,
                                event_id=event_id,
                                event=event,
                                sport=sport,
                                market=market,
                                selection=label,
                                odds=odd_row.get(field),
                                bookmaker=book,
                                observed_at=fetched_at,
                                source_url=source_url,
                                bookmaker_url=deep_link,
                                source_name="Odds-API.io",
                                link_exact=link_exact,
                            )
                    continue

                if low in {"spread", "spreads", "handicap"}:
                    for odd_row in odds_rows:
                        hdp = odd_row.get("hdp")
                        if hdp is None:
                            continue
                        market = f"Handicap {hdp}"
                        for field, label in (("home", "1"), ("away", "2")):
                            _append_quote(
                                rows,
                                event_id=event_id,
                                event=event,
                                sport=sport,
                                market=market,
                                selection=label,
                                odds=odd_row.get(field),
                                bookmaker=book,
                                observed_at=fetched_at,
                                source_url=source_url,
                                bookmaker_url=deep_link,
                                source_name="Odds-API.io",
                                link_exact=link_exact,
                            )
                    continue

                if low in {"both teams to score", "btts", "both teams score"}:
                    market = "Both Teams To Score"
                    for odd_row in odds_rows:
                        for field, label in (("yes", "Yes"), ("no", "No")):
                            _append_quote(
                                rows,
                                event_id=event_id,
                                event=event,
                                sport=sport,
                                market=market,
                                selection=label,
                                odds=odd_row.get(field),
                                bookmaker=book,
                                observed_at=fetched_at,
                                source_url=source_url,
                                bookmaker_url=deep_link,
                                source_name="Odds-API.io",
                                link_exact=link_exact,
                            )
    return list(rows.values())


async def scan_odds_api_io(*, api_key: str, timeout: float = 18.0,
                           max_events: int = 80, sports: tuple[str, ...] | None = None
                           ) -> tuple[list[dict], list[str], dict]:
    if not api_key:
        return [], [], {"configured": False, "provider": "Odds-API.io", "markets": 0, "events": 0}

    errors: list[str] = []
    requests = 0
    fetched_at = time.time()
    sports = sports or ODDS_API_IO_DEFAULT_SPORTS
    selected_books: list[str] = []
    events_by_id: dict[str, dict] = {}

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), headers={"Accept": "application/json"}) as client:
        try:
            response = await client.get(
                "https://api.odds-api.io/v3/bookmakers/selected",
                params={"apiKey": api_key},
            )
            requests += 1
            response.raise_for_status()
            body = response.json()
            if isinstance(body, dict):
                items = body.get("bookmakers") or body.get("data") or []
            else:
                items = body
            for entry in items if isinstance(items, list) else []:
                name = entry.get("name") if isinstance(entry, dict) else entry
                if str(name) in ODDS_API_IO_WANTED_BOOKS:
                    selected_books.append(str(name))
        except Exception as exc:
            errors.append(f"bookmakers/selected: {type(exc).__name__}: {exc}")

        # If the selected endpoint is unavailable, still try documented names. A 4xx will be
        # reported honestly rather than silently producing fake data.
        if not selected_books:
            selected_books = list(ODDS_API_IO_WANTED_BOOKS)

        discovery_book = selected_books[0]
        sem = asyncio.Semaphore(4)

        async def discover(sport: str):
            nonlocal requests
            async with sem:
                try:
                    response = await client.get(
                        "https://api.odds-api.io/v3/events",
                        params={
                            "apiKey": api_key,
                            "sport": sport,
                            "bookmaker": discovery_book,
                            "status": "pending",
                            "limit": max(10, min(100, int(max_events))),
                        },
                    )
                    requests += 1
                    response.raise_for_status()
                    body = response.json()
                    if isinstance(body, dict):
                        body = body.get("events") or body.get("data") or []
                    return sport, body if isinstance(body, list) else [], None
                except Exception as exc:
                    return sport, [], f"events {sport}: {type(exc).__name__}: {exc}"

        discoveries = await asyncio.gather(*(discover(s) for s in sports))
        for _, event_items, error in discoveries:
            if error:
                errors.append(error)
            for event_obj in event_items:
                if isinstance(event_obj, dict) and event_obj.get("id") is not None:
                    events_by_id[str(event_obj.get("id"))] = event_obj

        # Soonest events first, cap request volume, batch 10 events per documented endpoint.
        events = list(events_by_id.values())
        events.sort(key=lambda x: str(x.get("date") or ""))
        event_ids = [str(x.get("id")) for x in events[:max(1, int(max_events))]]
        odds_items: list[dict] = []
        books_csv = ",".join(selected_books[:30])

        for i in range(0, len(event_ids), 10):
            batch = event_ids[i:i + 10]
            try:
                response = await client.get(
                    "https://api.odds-api.io/v3/odds/multi",
                    params={
                        "apiKey": api_key,
                        "eventIds": ",".join(batch),
                        "bookmakers": books_csv,
                    },
                )
                requests += 1
                response.raise_for_status()
                body = response.json()
                if isinstance(body, dict):
                    body = body.get("data") or body.get("events") or []
                if isinstance(body, list):
                    odds_items.extend(x for x in body if isinstance(x, dict))
            except Exception as exc:
                errors.append(f"odds/multi batch {i//10 + 1}: {type(exc).__name__}: {exc}")

    rows = parse_odds_api_io_events(odds_items, fetched_at=fetched_at)
    return rows, errors, {
        "configured": True,
        "provider": "Odds-API.io",
        "ok": bool(rows),
        "events": len({str(x.get("id")) for x in odds_items if isinstance(x, dict)}),
        "markets": len(rows),
        "requests": requests,
        "selected_bookmakers": selected_books,
    }


def _extract_external_event_ids(candidates) -> tuple[set[str], set[str]]:
    arbiscan: set[str] = set()
    odds_api_io: set[str] = set()
    for candidate in candidates or []:
        legs = getattr(candidate, "legs", None)
        if legs is None and isinstance(candidate, dict):
            legs = candidate.get("legs") or []
        for leg in legs or []:
            source_url = getattr(leg, "source_url", None)
            if source_url is None and isinstance(leg, dict):
                source_url = leg.get("source_url")
            url = str(source_url or "")
            m = re.search(r"api\.arbiscan\.pl/v1/events/([^/?#]+)", url)
            if m:
                arbiscan.add(m.group(1))
            m = re.search(r"api\.odds-api\.io/v3/odds\?eventId=([^&#]+)", url)
            if m:
                odds_api_io.add(m.group(1))
    return arbiscan, odds_api_io


async def confirm_odds_api_io(*, api_key: str, event_ids: set[str], timeout: float = 14.0
                              ) -> tuple[list[dict], list[str], dict]:
    if not api_key or not event_ids:
        return [], [], {"configured": bool(api_key), "provider": "Odds-API.io confirm", "markets": 0}
    errors: list[str] = []
    items: list[dict] = []
    requests = 0
    fetched_at = time.time()
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), headers={"Accept": "application/json"}) as client:
        selected_books = list(ODDS_API_IO_WANTED_BOOKS)
        try:
            response = await client.get("https://api.odds-api.io/v3/bookmakers/selected", params={"apiKey": api_key})
            requests += 1
            response.raise_for_status()
            body = response.json()
            values = body.get("bookmakers") if isinstance(body, dict) else body
            picked = []
            for entry in values if isinstance(values, list) else []:
                name = entry.get("name") if isinstance(entry, dict) else entry
                if str(name) in ODDS_API_IO_WANTED_BOOKS:
                    picked.append(str(name))
            if picked:
                selected_books = picked
        except Exception as exc:
            errors.append(f"selected confirm: {type(exc).__name__}: {exc}")

        ids = sorted(event_ids)[:40]
        for i in range(0, len(ids), 10):
            try:
                response = await client.get(
                    "https://api.odds-api.io/v3/odds/multi",
                    params={
                        "apiKey": api_key,
                        "eventIds": ",".join(ids[i:i + 10]),
                        "bookmakers": ",".join(selected_books[:30]),
                    },
                )
                requests += 1
                response.raise_for_status()
                body = response.json()
                if isinstance(body, dict):
                    body = body.get("data") or body.get("events") or []
                if isinstance(body, list):
                    items.extend(x for x in body if isinstance(x, dict))
            except Exception as exc:
                errors.append(f"confirm batch {i//10 + 1}: {type(exc).__name__}: {exc}")
    rows = parse_odds_api_io_events(items, fetched_at=fetched_at)
    return rows, errors, {
        "configured": True,
        "provider": "Odds-API.io confirm",
        "events": len(items),
        "markets": len(rows),
        "requests": requests,
        "ok": bool(rows),
    }


async def scan_external_feeds() -> tuple[list[dict], list[str], dict]:
    """Run every configured documented feed in parallel."""
    arb_key = os.getenv("ARBISCAN_API_KEY", "").strip()
    odds_key = os.getenv("ODDS_API_IO_KEY", "").strip()
    timeout = float(os.getenv("EXTERNAL_FEEDS_TIMEOUT", "18") or 18)
    max_pages = int(os.getenv("ARBISCAN_MAX_PAGES", "1") or 1)
    max_events = int(os.getenv("ODDS_API_IO_MAX_EVENTS", "80") or 80)
    sports_raw = os.getenv("ODDS_API_IO_SPORTS", "").strip()
    sports = tuple(x.strip() for x in sports_raw.split(",") if x.strip()) or ODDS_API_IO_DEFAULT_SPORTS

    jobs = {
        "ArbiScan API": scan_arbiscan(
            api_key=arb_key,
            timeout=timeout,
            max_pages=max_pages,
            max_age_seconds=int(os.getenv("MAX_QUOTE_AGE_SECONDS", "300") or 300),
        ),
        "Odds-API.io": scan_odds_api_io(
            api_key=odds_key,
            timeout=timeout,
            max_events=max_events,
            sports=sports,
        ),
    }
    results = await asyncio.gather(*jobs.values(), return_exceptions=True)
    rows: list[dict] = []
    errors: list[str] = []
    providers: dict[str, dict] = {}
    for name, result in zip(jobs, results):
        if isinstance(result, BaseException):
            providers[name] = {"configured": bool(arb_key if name == "ArbiScan API" else odds_key), "ok": False, "markets": 0}
            errors.append(f"{name}: {type(result).__name__}: {result}")
            continue
        provider_rows, provider_errors, stats = result
        rows.extend(provider_rows)
        errors.extend(f"{name}: {x}" for x in provider_errors)
        providers[name] = stats
    return rows, errors, {
        "enabled": bool(arb_key or odds_key),
        "configured_count": int(bool(arb_key)) + int(bool(odds_key)),
        "markets": len(rows),
        "providers": providers,
    }


async def confirm_external_feeds(candidates) -> tuple[list[dict], list[str], dict]:
    """Re-fetch API-backed candidate events just before alerting."""
    arb_key = os.getenv("ARBISCAN_API_KEY", "").strip()
    odds_key = os.getenv("ODDS_API_IO_KEY", "").strip()
    arb_ids, odds_ids = _extract_external_event_ids(candidates)
    jobs = []
    names = []
    if arb_key and arb_ids:
        names.append("ArbiScan API")
        jobs.append(confirm_arbiscan(api_key=arb_key, event_ids=arb_ids))
    if odds_key and odds_ids:
        names.append("Odds-API.io")
        jobs.append(confirm_odds_api_io(api_key=odds_key, event_ids=odds_ids))
    if not jobs:
        return [], [], {"markets": 0, "providers": {}}

    results = await asyncio.gather(*jobs, return_exceptions=True)
    rows: list[dict] = []
    errors: list[str] = []
    providers = {}
    for name, result in zip(names, results):
        if isinstance(result, BaseException):
            errors.append(f"{name}: {type(result).__name__}: {result}")
            providers[name] = {"ok": False, "markets": 0}
            continue
        provider_rows, provider_errors, stats = result
        rows.extend(provider_rows)
        errors.extend(f"{name}: {x}" for x in provider_errors)
        providers[name] = stats
    return rows, errors, {"markets": len(rows), "providers": providers}
