from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import httpx
from bs4 import BeautifulSoup

from ..models import Quote


ODDS_RE = re.compile(r"(?<!\d)(\d{1,3}[\.,]\d{2})(?!\d)")
SKIP_MARKETS = {"szczegóły", "składy", "h2h", "tabela", "kursy"}


@dataclass
class EventRef:
    url: str
    event: str
    sport: str


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def odds_from_text(value: str) -> float | None:
    match = ODDS_RE.search(value or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def market_slug(label: str, source_html: str = "") -> str | None:
    label = clean(label)
    low = label.lower()

    # If the page exposes a real market URL/data attribute, prefer it.
    pattern = re.compile(r"market=([a-zA-Z0-9_-]+)")
    nearby = source_html[:]
    hit = pattern.search(nearby)
    if hit and clean(label).lower() in nearby.lower():
        return hit.group(1)

    direct = {
        "1x2": "1x2",
        "1x / x2 / 12": "doublechance",
        "u/o 1.5": "under15",
        "u/o 2.5": "over25",
        "u/o 3.5": "over35",
        "bts": "bts",
        "dnb": "dnb",
        "h -2.5": "handicap_-2_5",
        "h -1.5": "handicap_-1_5",
        "h -0.5": "handicap_-0_5",
        "h +0.5": "handicap_+0_5",
        "h +1.5": "handicap_+1_5",
        "h +2.5": "handicap_+2_5",
    }
    if low in direct:
        return direct[low]

    # Generic slug fallback. This lets newly added markets be attempted
    # without changing the scanner code.
    slug = re.sub(r"[^a-z0-9]+", "_", low.replace("/", "_")).strip("_")
    return slug or None


class DobryBukHTTP:
    def __init__(self, base_url: str, concurrency: int = 12, timeout: float = 18):
        self.base_url = base_url
        self.sem = asyncio.Semaphore(concurrency)
        self.timeout = timeout
        self.client: httpx.AsyncClient | None = None

    async def start(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=8),
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154 Safari/537.36"
                ),
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.6",
            },
            follow_redirects=True,
        )

    async def stop(self):
        if self.client:
            await self.client.aclose()

    async def get(self, url: str) -> str:
        assert self.client is not None
        async with self.sem:
            for attempt in range(3):
                try:
                    response = await self.client.get(url)
                    response.raise_for_status()
                    return response.text
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.4 * (attempt + 1))
        return ""

    def discover_events(self, html: str, max_events: int = 80) -> list[EventRef]:
        soup = BeautifulSoup(html, "html.parser")
        links = []
        seen = set()

        # The public page contains event links for the currently listed
        # sports; no hard-coded sport whitelist is used.
        for a in soup.find_all("a", href=True):
            href = urljoin(self.base_url, a["href"])
            if "/kursy/mecz/" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            name = clean(a.get_text(" ", strip=True))
            if len(name) < 3:
                continue

            sport = self._infer_sport(a)
            links.append(EventRef(href, name, sport))
            if len(links) >= max_events:
                break

        return links

    def _infer_sport(self, anchor) -> str:
        known = [
            "Piłka nożna", "Tenis", "Koszykówka", "Hokej", "Piłka ręczna",
            "MMA", "Boks", "Żużel", "Baseball", "Futbol amerykański",
            "Tenis stołowy", "Siatkówka", "Rugby", "Dart", "Snooker",
            "Futsal", "Golf", "Formuła 1", "Kolarstwo", "Esport",
        ]
        node = anchor
        for _ in range(7):
            if node is None:
                break
            text = clean(node.get_text(" ", strip=True))
            for sport in known:
                if sport.lower() in text.lower():
                    return sport
            node = node.parent
        return "Inne"

    def market_buttons(self, html: str) -> list[tuple[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        result = []
        seen = set()

        for node in soup.find_all(["button", "a"]):
            label = clean(node.get_text(" ", strip=True))
            if not label or label.lower() in SKIP_MARKETS:
                continue

            raw = str(node)
            href = node.get("href", "")
            slug = None

            # Prefer explicit machine-readable market identifiers.
            for attr in ("data-market", "data-value", "value", "data-testid"):
                value = node.get(attr)
                if value and ("market" in attr or attr in ("data-value", "value")):
                    candidate = clean(str(value))
                    if candidate and len(candidate) < 80:
                        slug = candidate
                        break

            for attr in ("hx-get", "data-url", "data-href", "onclick"):
                value = node.get(attr, "")
                if value and "market=" in value:
                    slug = parse_qs(urlparse(value.split("market=", 1)[0] + "?" + value.split("?",1)[-1]).query).get("market", [None])[0] or slug

            if not slug and "market=" in href:
                slug = parse_qs(urlparse(href).query).get("market", [None])[0]

            # If the source exposes only visible text, generate a best-effort
            # slug. This is deliberately generic so newly-added market labels
            # are attempted without a hard-coded whitelist.
            if not slug:
                slug = market_slug(label, raw)

            # Ignore obvious non-market controls (dates, login, pagination).
            low = label.lower()
            looks_like_market = (
                slug is not None and (
                    any(x in low for x in (
                        "1x2", "1x / x2", "u/o", "bts", "dnb", "h ", "strzał",
                        "faule", "spalone", "celne", "winner", "zwyci", "kart",
                        "set", "gemy", "punkty", "rzuty", "rogi", "ofsajd",
                        "podwój", "oba", "tak", "nie",
                    ))
                    or any(x in str(node).lower() for x in ("data-market", "market="))
                )
            )
            if not looks_like_market:
                continue

            key = (label.lower(), slug)
            if slug and key not in seen:
                seen.add(key)
                result.append((label, slug))

        # Always include the default market.
        if not any(x[1] == "1x2" for x in result):
            result.insert(0, ("1x2", "1x2"))
        return result

    def _set_market(self, url: str, slug: str) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        query["market"] = [slug]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    def parse_market(self, html: str, event: EventRef, source_url: str) -> dict | None:
        soup = BeautifulSoup(html, "html.parser")
        table = None

        for candidate in soup.find_all("table"):
            headers = [clean(x.get_text(" ", strip=True)).lower() for x in candidate.find_all("th")]
            if "bukmacher" in " ".join(headers):
                table = candidate
                break

        if not table:
            return None

        rows = table.find_all("tr")
        if not rows:
            return None

        header_cells = rows[0].find_all(["th", "td"])
        headers = [clean(x.get_text(" ", strip=True)) for x in header_cells]
        if not headers:
            return None

        selections = headers[1:]
        quotes: dict[str, list[Quote]] = {x: [] for x in selections if x}

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            bookmaker = clean(cells[0].get_text(" ", strip=True))
            if not bookmaker or bookmaker.lower() in {"bukmacher", "bookmaker"}:
                continue

            bookmaker_url = ""
            link = cells[0].find("a", href=True)
            if link:
                bookmaker_url = urljoin(source_url, link["href"])

            for index, cell in enumerate(cells[1:]):
                if index >= len(selections):
                    break
                selection = selections[index]
                if not selection:
                    continue

                odd = odds_from_text(cell.get_text(" ", strip=True))
                if odd is None or odd <= 1:
                    continue

                quotes.setdefault(selection, []).append(
                    Quote(
                        selection=selection,
                        odds=odd,
                        bookmaker=bookmaker,
                        observed_at=time.time(),
                        source_url=source_url,
                        bookmaker_url=bookmaker_url,
                    )
                )

        quotes = {k: v for k, v in quotes.items() if v}
        if not quotes:
            return None

        # Use the visible market labels from the table rather than a hard-coded
        # market whitelist.
        market = " / ".join(quotes.keys())
        return {
            "event": event.event,
            "sport": event.sport,
            "market": market,
            "quotes": quotes,
            "source_url": source_url,
        }

    async def scan_event(self, event: EventRef, max_markets: int = 40):
        errors = []
        try:
            base_html = await self.get(event.url)
            markets = self.market_buttons(base_html)[:max_markets]
            urls = [(label, self._set_market(event.url, slug)) for label, slug in markets]

            async def one(label, url):
                try:
                    html = await self.get(url)
                    parsed = self.parse_market(html, event, url)
                    return parsed
                except Exception as exc:
                    errors.append(f"{event.event} / {label}: {exc}")
                    return None

            results = await asyncio.gather(*(one(*x) for x in urls))
            return [x for x in results if x], errors
        except Exception as exc:
            return [], [f"{event.event}: {exc}"]

    async def scan(self, max_events: int = 80, max_markets: int = 40):
        started = time.time()
        main_html = await self.get(self.base_url)
        events = self.discover_events(main_html, max_events)

        batches = await asyncio.gather(
            *(self.scan_event(event, max_markets) for event in events)
        )

        all_markets = []
        errors = []
        for data, errs in batches:
            all_markets.extend(data)
            errors.extend(errs)

        return {
            "events": events,
            "markets": all_markets,
            "errors": errors[-100:],
            "elapsed": round(time.time() - started, 2),
        }
