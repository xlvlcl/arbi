from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class DirectSource:
    bookmaker: str
    urls: tuple[str, ...]
    base_url: str


DIRECT_SOURCES: tuple[DirectSource, ...] = (
    DirectSource("Betclic", ("https://www.betclic.pl/",), "https://www.betclic.pl/"),
    DirectSource("Superbet", ("https://superbet.pl/zaklady-bukmacherskie",), "https://superbet.pl/"),
    DirectSource("Fortuna", ("https://www.efortuna.pl/",), "https://www.efortuna.pl/"),
    DirectSource("STS", ("https://www.sts.pl/",), "https://www.sts.pl/"),
    DirectSource("Betfan", ("https://betfan.pl/",), "https://betfan.pl/"),
    DirectSource("Forbet", ("https://www.iforbet.pl/",), "https://www.iforbet.pl/"),
    DirectSource("LVBet", ("https://lvbet.pl/",), "https://lvbet.pl/"),
    DirectSource("ETOTO", ("https://www.etoto.pl/",), "https://www.etoto.pl/"),
    DirectSource("Fuksiarz", ("https://fuksiarz.pl/",), "https://fuksiarz.pl/"),
)

# Deliberately conservative. Direct parsers only emit rows that look complete enough
# for a safe 1X2 / two-way winner interpretation. Ambiguous DOM fragments are skipped.
DECIMAL_ODDS_RE = re.compile(r"(?<!\d)(\d{1,3}[\.,]\d{1,2})(?!\d)")
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b")
SCORE_RE = re.compile(r"\b\d{1,2}\s*[-:]\s*\d{1,2}\b")
EVENT_ID_RE = re.compile(r"(?:^|[-_/])m\d{5,}(?:$|[/?#])", re.I)

SPORT_HINTS = {
    "pilka-nozna": "Piłka nożna",
    "football": "Piłka nożna",
    "soccer": "Piłka nożna",
    "tenis-stolowy": "Tenis stołowy",
    "table-tennis": "Tenis stołowy",
    "tenis": "Tenis",
    "tennis": "Tenis",
    "koszykowka": "Koszykówka",
    "basketball": "Koszykówka",
    "siatkowka": "Siatkówka",
    "volleyball": "Siatkówka",
    "hokej": "Hokej",
    "hockey": "Hokej",
    "pilka-reczna": "Piłka ręczna",
    "handball": "Piłka ręczna",
    "baseball": "Baseball",
    "futbol-amerykanski": "Futbol amerykański",
    "american-football": "Futbol amerykański",
    "rugby": "Rugby",
    "dart": "Dart",
    "snooker": "Snooker",
    "mma": "MMA",
    "boks": "Boks",
    "boxing": "Boks",
    "esport": "Esport",
    "counter-strike": "Esport",
    "cs2": "Esport",
    "league-of-legends": "Esport",
    "dota": "Esport",
    "badminton": "Badminton",
    "golf": "Golf",
    "cricket": "Krykiet",
    "krykiet": "Krykiet",
    "formula-1": "Formuła 1",
    "formula1": "Formuła 1",
    "f1": "Formuła 1",
    "cycling": "Kolarstwo",
    "kolarstwo": "Kolarstwo",
    "biathlon": "Biathlon",
    "biathlon": "Biathlon",
    "ski-jumping": "Skoki narciarskie",
    "skoki-narciarskie": "Skoki narciarskie",
    "skiing": "Narciarstwo",
    "narciarstwo": "Narciarstwo",
    "futsal": "Futsal",
    "water-polo": "Piłka wodna",
    "pilka-wodna": "Piłka wodna",
    "field-hockey": "Hokej na trawie",
    "hokej-na-trawie": "Hokej na trawie",
    "motorsport": "Motorsport",
}


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


def _ascii(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in value if not unicodedata.combining(ch)).lower()


def infer_sport(url: str, text: str = "") -> str:
    hay = _ascii(url + " " + text).replace("_", "-").replace(" ", "-")
    for token, sport in SPORT_HINTS.items():
        if token in hay:
            return sport
    return "Inne"


def _odds(text: str) -> list[float]:
    # Remove timestamps / dates / scores before odds parsing to avoid 20:45 or 2-1.
    value = TIME_RE.sub(" ", text or "")
    value = DATE_RE.sub(" ", value)
    value = SCORE_RE.sub(" ", value)
    out: list[float] = []
    for token in DECIMAL_ODDS_RE.findall(value):
        try:
            number = float(token.replace(",", "."))
        except ValueError:
            continue
        if 1.01 <= number <= 1000:
            out.append(number)
    return out


def _event_name_from_href(href: str, fallback_text: str) -> str:
    path = urlparse(href).path.rstrip("/")
    slug = path.split("/")[-1] if path else ""
    slug = re.sub(r"-m\d+$", "", slug, flags=re.I)
    slug = re.sub(r"-\d{6,}$", "", slug)
    slug = re.sub(r"[-_]+", " ", slug)
    slug = clean(slug)
    if len(slug) >= 5 and any(ch.isalpha() for ch in slug):
        return slug.title()

    # Fallback: take the part before the first decimal odd and strip time/date fragments.
    text = TIME_RE.sub(" ", fallback_text or "")
    text = DATE_RE.sub(" ", text)
    match = DECIMAL_ODDS_RE.search(text)
    if match:
        text = text[: match.start()]
    text = re.sub(r"\b(remis|draw|x)\b", " ", text, flags=re.I)
    text = clean(text.strip(" -–—|"))
    return text[:160]


def _looks_like_event_link(href: str, text: str) -> bool:
    low = _ascii(href)
    txt = _ascii(text)
    if EVENT_ID_RE.search(href):
        return True
    if any(token in low for token in ("/mecz", "/match", "/event", "/wydarzenie")):
        return len(_odds(text)) >= 2
    # Some homepages use opaque links but the anchor text itself contains a complete market.
    return len(_odds(text)) >= 2 and any(marker in txt for marker in ("remis", " - ", " vs ", " v "))


def parse_direct_listing(html: str, source: DirectSource) -> list[dict]:
    """Parse conservative direct-market rows from a bookmaker page.

    This is intentionally best-effort and safe: a row is emitted only when the DOM already
    contains a complete 3-way result or a clearly two-way event. It does not invent missing
    selections and therefore cannot create the old X+2 false-surebet class of bugs.
    """
    soup = BeautifulSoup(html, "html.parser")
    now = time.time()
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for a in soup.find_all("a", href=True):
        href = urljoin(source.base_url, a.get("href", ""))
        text = clean(a.get_text(" ", strip=True))
        if not href or not text or not _looks_like_event_link(href, text):
            continue

        values = _odds(text)
        low = _ascii(text)
        market = ""
        selections: list[str] = []
        odds_values: list[float] = []

        # Three-way result is safe only when the text explicitly contains a draw cue.
        if len(values) >= 3 and ("remis" in low or re.search(r"\bx\b", low)):
            market = "1X2"
            selections = ["1", "X", "2"]
            odds_values = values[-3:]
        elif len(values) == 2 and not ("remis" in low or re.search(r"\bx\b", low)):
            market = "Winner"
            selections = ["1", "2"]
            odds_values = values
        else:
            continue

        event = _event_name_from_href(href, text)
        if len(event) < 5:
            continue

        key = (href, market)
        if key in seen:
            continue
        seen.add(key)

        quotes = {}
        for selection, odd in zip(selections, odds_values):
            quotes[selection] = [
                {
                    "selection": selection,
                    "odds": odd,
                    "bookmaker": source.bookmaker,
                    "observed_at": now,
                    "source_url": href,
                    "bookmaker_url": href,
                    "source_name": f"{source.bookmaker} direct",
                }
            ]

        rows.append(
            {
                "event": event,
                "sport": infer_sport(href, text),
                "market": market,
                "quotes": quotes,
                "observed_at": now,
                "source_url": href,
                "event_url": href,
                "source_name": f"{source.bookmaker} direct",
            }
        )

    return rows


async def scan_direct_books(
    enabled: bool = True,
    timeout: float = 12.0,
    concurrency: int = 5,
) -> tuple[list[dict], list[str], dict]:
    if not enabled:
        return [], [], {"enabled": False, "sources": {}}

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.6",
        "Cache-Control": "no-cache",
    }
    sem = asyncio.Semaphore(max(1, concurrency))
    errors: list[str] = []
    all_rows: list[dict] = []
    stats: dict[str, dict] = {}

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=httpx.Timeout(timeout, connect=min(timeout, 8.0)),
        limits=httpx.Limits(max_connections=max(8, concurrency * 2), max_keepalive_connections=8),
    ) as client:

        async def one(source: DirectSource):
            source_rows: list[dict] = []
            source_errors: list[str] = []
            bytes_total = 0
            async with sem:
                for url in source.urls:
                    try:
                        response = await client.get(url)
                        response.raise_for_status()
                        html = response.text
                        bytes_total += len(html.encode("utf-8", errors="ignore"))
                        source_rows.extend(parse_direct_listing(html, source))
                    except Exception as exc:
                        source_errors.append(f"{url}: {type(exc).__name__}: {exc}")
            # Dedupe within the bookmaker.
            unique: dict[tuple[str, str], dict] = {}
            for row in source_rows:
                key = (row.get("event_url", ""), row.get("market", ""))
                unique[key] = row
            return source, list(unique.values()), source_errors, bytes_total

        results = await asyncio.gather(*(one(source) for source in DIRECT_SOURCES))

    for source, rows, source_errors, bytes_total in results:
        all_rows.extend(rows)
        errors.extend(f"{source.bookmaker}: {msg}" for msg in source_errors)
        stats[source.bookmaker] = {
            "markets": len(rows),
            "html_bytes": bytes_total,
            "ok": bool(rows) or not source_errors,
        }

    return all_rows, errors, {"enabled": True, "sources": stats, "markets": len(all_rows)}
