from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext


@dataclass(frozen=True)
class DirectSource:
    bookmaker: str
    urls: tuple[str, ...]
    base_url: str
    priority: int = 100


# v29: direct bookmaker pages are a real fallback, not only a cosmetic source-health check.
# The first six are intentionally prioritised because they are the most useful Polish books
# for cross-book comparison. Only ordinary public pages are used; there is no CAPTCHA or
# anti-bot bypass here.
DIRECT_SOURCES: tuple[DirectSource, ...] = (
    DirectSource("Betclic", ("https://www.betclic.pl/",), "https://www.betclic.pl/", 1),
    DirectSource("Fortuna", ("https://www.efortuna.pl/zaklady-bukmacherskie",), "https://www.efortuna.pl/", 2),
    DirectSource("STS", ("https://www.sts.pl/zaklady-bukmacherskie",), "https://www.sts.pl/", 3),
    DirectSource("Superbet", ("https://superbet.pl/zaklady-bukmacherskie",), "https://superbet.pl/", 4),
    DirectSource("Betfan", ("https://betfan.pl/",), "https://betfan.pl/", 5),
    DirectSource("Forbet", ("https://www.iforbet.pl/",), "https://www.iforbet.pl/", 6),
    DirectSource("LVBet", ("https://lvbet.pl/",), "https://lvbet.pl/", 20),
    DirectSource("ETOTO", ("https://www.etoto.pl/",), "https://www.etoto.pl/", 21),
    DirectSource("Fuksiarz", ("https://fuksiarz.pl/",), "https://fuksiarz.pl/", 22),
    DirectSource("TotalBet", ("https://totalbet.pl/",), "https://totalbet.pl/", 23),
    DirectSource("Betters", ("https://betters.pl/",), "https://betters.pl/", 24),
    DirectSource("LeBull", ("https://lebull.pl/",), "https://lebull.pl/", 25),
    DirectSource("AdmiralBet", ("https://admiralbet.pl/",), "https://admiralbet.pl/", 26),
    DirectSource("BetSport", ("https://betsport.pl/",), "https://betsport.pl/", 27),
    DirectSource("ComeOn", ("https://comeon.pl/",), "https://comeon.pl/", 28),
    DirectSource("PZBuk", ("https://pzbuk.pl/",), "https://pzbuk.pl/", 29),
)

# Deliberately conservative. Direct parsers only emit rows that look complete enough
# for a safe 1X2 / two-way winner interpretation. Ambiguous DOM fragments are skipped.
DECIMAL_ODDS_RE = re.compile(r"(?<!\d)(\d{1,3}[\.,]\d{1,2})(?!\d)")
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b")
SCORE_RE = re.compile(r"\b\d{1,2}\s*[-:]\s*\d{1,2}\b")
EVENT_ID_RE = re.compile(r"(?:^|[-_/])m\d{5,}(?:$|[/?#])", re.I)
GENERIC_SLUGS = {
    "zaklady-bukmacherskie", "sport", "sports", "mecze", "matches", "events",
    "live", "oferta", "home", "index", "pilka-nozna", "tenis", "koszykowka",
}
BLOCK_MARKERS = (
    "sorry, you have been blocked",
    "you are unable to access",
    "attention required! | cloudflare",
    "access denied",
    "request blocked",
)

SPORT_HINTS = {
    "pilka-nozna": "Piłka nożna", "football": "Piłka nożna", "soccer": "Piłka nożna",
    "tenis-stolowy": "Tenis stołowy", "table-tennis": "Tenis stołowy",
    "tenis": "Tenis", "tennis": "Tenis",
    "koszykowka": "Koszykówka", "basketball": "Koszykówka",
    "siatkowka": "Siatkówka", "volleyball": "Siatkówka",
    "hokej": "Hokej", "hockey": "Hokej",
    "pilka-reczna": "Piłka ręczna", "handball": "Piłka ręczna",
    "baseball": "Baseball", "futbol-amerykanski": "Futbol amerykański",
    "american-football": "Futbol amerykański", "rugby": "Rugby", "dart": "Dart",
    "snooker": "Snooker", "mma": "MMA", "boks": "Boks", "boxing": "Boks",
    "esport": "Esport", "counter-strike": "Esport", "cs2": "Esport",
    "league-of-legends": "Esport", "dota": "Esport", "badminton": "Badminton",
    "golf": "Golf", "cricket": "Krykiet", "krykiet": "Krykiet",
    "formula-1": "Formuła 1", "formula1": "Formuła 1", "f1": "Formuła 1",
    "cycling": "Kolarstwo", "kolarstwo": "Kolarstwo", "biathlon": "Biathlon",
    "ski-jumping": "Skoki narciarskie", "skoki-narciarskie": "Skoki narciarskie",
    "skiing": "Narciarstwo", "narciarstwo": "Narciarstwo", "futsal": "Futsal",
    "water-polo": "Piłka wodna", "pilka-wodna": "Piłka wodna",
    "field-hockey": "Hokej na trawie", "hokej-na-trawie": "Hokej na trawie",
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


def _blocked_text(text: str) -> bool:
    low = _ascii(text)
    return any(marker in low for marker in BLOCK_MARKERS)


def _event_name_from_href(href: str, fallback_text: str) -> str:
    path = urlparse(href).path.rstrip("/")
    slug = path.split("/")[-1] if path else ""
    raw_slug = slug.lower()
    slug = re.sub(r"-m\d+$", "", slug, flags=re.I)
    slug = re.sub(r"-\d{6,}$", "", slug)
    slug = re.sub(r"[-_]+", " ", slug)
    slug = clean(slug)
    if raw_slug not in GENERIC_SLUGS and len(slug) >= 5 and any(ch.isalpha() for ch in slug):
        return slug.title()

    # Fallback: take the part before the first decimal odd and strip time/date fragments.
    text = TIME_RE.sub(" ", fallback_text or "")
    text = DATE_RE.sub(" ", text)
    match = DECIMAL_ODDS_RE.search(text)
    if match:
        text = text[: match.start()]
    text = re.sub(r"\b(remis|draw|kurs|odds|typ|bet)\b", " ", text, flags=re.I)
    text = clean(text.strip(" -–—|"))
    # Keep the tail for containers that start with league/date labels.
    if len(text) > 160:
        text = text[-160:]
    return text[:160]


def _eventish_href(href: str) -> bool:
    low = _ascii(href)
    if EVENT_ID_RE.search(href):
        return True
    if any(token in low for token in ("/mecz", "/match", "/event", "/wydarzenie", "/spotkanie")):
        return True
    # Betclic-like event slugs and many sportsbook event URLs end in a long numeric id.
    path = urlparse(href).path.rstrip("/")
    tail = path.split("/")[-1] if path else ""
    return bool(re.search(r"(?:-|_)\d{7,}$", tail)) or bool(re.search(r"-m\d{5,}$", tail, re.I))


def _candidate_texts(anchor) -> list[str]:
    """Anchor text plus the smallest nearby DOM blocks containing a complete market.

    Many sportsbook UIs put team names in an <a> and odds in sibling <button>s. v28 only
    parsed the anchor itself, so rendered Betclic/Fortuna/STS pages could be reachable but
    still produce zero rows. v29 inspects a few small ancestors while rejecting huge page
    containers to keep the parser conservative.
    """
    values: list[str] = []
    seen: set[str] = set()

    node = anchor
    for depth in range(5):
        try:
            text = clean(node.get_text(" ", strip=True))
        except Exception:
            text = ""
        if text and text not in seen:
            seen.add(text)
            odds = _odds(text)
            if depth == 0 or (2 <= len(odds) <= 8 and len(text) <= 900):
                values.append(text)
        node = getattr(node, "parent", None)
        if node is None:
            break
    return values


def _market_from_text(text: str) -> tuple[str, list[str], list[float]] | None:
    values = _odds(text)
    low = _ascii(text)
    has_draw = "remis" in low or " draw " in f" {low} " or bool(re.search(r"(?:^|\s)x(?:\s|$)", low))
    if len(values) >= 3 and has_draw:
        return "1X2", ["1", "X", "2"], values[-3:]
    if len(values) == 2 and not has_draw:
        return "Winner", ["1", "2"], values
    return None


def parse_direct_listing(html: str, source: DirectSource) -> list[dict]:
    """Parse safe 1X2 / two-way markets from a public bookmaker page.

    The parser does not invent selections. It supports both compact anchors (Betclic-like)
    and event cards where odds are siblings of the event link (common in modern JS UIs).
    """
    if _blocked_text(html):
        return []
    soup = BeautifulSoup(html, "html.parser")
    now = time.time()
    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for a in soup.find_all("a", href=True):
        href = urljoin(source.base_url, a.get("href", ""))
        if not href or not href.startswith(("http://", "https://")):
            continue

        candidates = _candidate_texts(a)
        if not candidates:
            continue
        eventish = _eventish_href(href)

        parsed = None
        chosen_text = ""
        for text in candidates:
            maybe = _market_from_text(text)
            if not maybe:
                continue
            low = _ascii(text)
            # For non-obvious URLs require an explicit event separator/draw cue.
            if not eventish and not any(marker in low for marker in ("remis", " - ", " vs ", " v ")):
                continue
            parsed = maybe
            chosen_text = text
            break
        if not parsed:
            continue

        market, selections, odds_values = parsed
        event = _event_name_from_href(href, chosen_text)
        if len(event) < 5 or not any(ch.isalpha() for ch in event):
            continue

        key = (_ascii(event), market.lower(), href)
        if key in seen:
            continue
        seen.add(key)

        quotes = {
            selection: [
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
            for selection, odd in zip(selections, odds_values)
        }
        rows.append(
            {
                "event": event,
                "sport": infer_sport(href, chosen_text),
                "market": market,
                "quotes": quotes,
                "observed_at": now,
                "source_url": href,
                "event_url": href,
                "source_name": f"{source.bookmaker} direct",
            }
        )

    return rows


async def scan_direct_books_browser(
    context: BrowserContext,
    *,
    enabled: bool = True,
    max_seconds: int = 75,
    concurrency: int = 4,
) -> tuple[list[dict], list[str], dict]:
    """Read public bookmaker pages in a normal browser.

    This is a resilient fallback when the comparison site is unavailable. There is no
    CAPTCHA solving, fingerprint masking, proxying, login bypass, or anti-bot evasion.
    """
    if not enabled:
        return [], [], {"enabled": False, "sources": {}, "markets": 0}

    started = time.monotonic()
    sem = asyncio.Semaphore(max(1, int(concurrency)))
    errors: list[str] = []
    all_rows: list[dict] = []
    stats: dict[str, dict] = {}

    async def one(source: DirectSource):
        page = None
        rows: list[dict] = []
        local_errors: list[str] = []
        loaded = False
        blocked = False
        try:
            async with sem:
                if time.monotonic() - started >= max_seconds:
                    return source, [], ["budget exhausted"], False, False
                page = await context.new_page()
                for url in source.urls:
                    if time.monotonic() - started >= max_seconds:
                        break
                    try:
                        response = await page.goto(url, wait_until="domcontentloaded", timeout=18000)
                        status = response.status if response else 0
                        if status and status >= 400:
                            local_errors.append(f"{url}: HTTP {status}")
                            continue
                        loaded = True
                        try:
                            await page.wait_for_load_state("networkidle", timeout=4000)
                        except Exception:
                            pass
                        await page.wait_for_timeout(1200)

                        # Ordinary cookie consent only.
                        for label in ("Akceptuj", "Akceptuj wszystkie", "Zgadzam się", "Accept", "Rozumiem"):
                            try:
                                btn = page.get_by_role("button", name=re.compile(label, re.I))
                                if await btn.count():
                                    await btn.first.click(timeout=1200)
                                    await page.wait_for_timeout(250)
                                    break
                            except Exception:
                                pass

                        for _ in range(5):
                            try:
                                await page.evaluate("() => window.scrollBy(0, Math.max(innerHeight*1.6,900))")
                            except Exception:
                                pass
                            await page.wait_for_timeout(320)

                        html = await page.content()
                        if _blocked_text(html):
                            blocked = True
                            local_errors.append(f"{url}: strona zablokowała runner GitHub")
                            continue
                        rows.extend(parse_direct_listing(html, source))
                    except Exception as exc:
                        local_errors.append(f"{url}: {type(exc).__name__}: {exc}")
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass

        unique: dict[tuple[str, str, str], dict] = {}
        for row in rows:
            unique[(row.get("event", ""), row.get("market", ""), row.get("event_url", ""))] = row
        return source, list(unique.values()), local_errors, loaded, blocked

    ordered = tuple(sorted(DIRECT_SOURCES, key=lambda s: s.priority))
    results = await asyncio.gather(*(one(source) for source in ordered))

    for source, rows, local_errors, loaded, blocked in results:
        all_rows.extend(rows)
        errors.extend(f"{source.bookmaker}: {msg}" for msg in local_errors)
        stats[source.bookmaker] = {
            "markets": len(rows),
            "loaded": bool(loaded),
            "blocked": bool(blocked),
            "ok": bool(rows) or (loaded and not local_errors),
            "mode": "public-browser-v29",
        }

    return all_rows, errors, {
        "enabled": True,
        "sources": stats,
        "markets": len(all_rows),
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }


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
            blocked = False
            async with sem:
                for url in source.urls:
                    try:
                        response = await client.get(url)
                        response.raise_for_status()
                        html = response.text
                        bytes_total += len(html.encode("utf-8", errors="ignore"))
                        if _blocked_text(html):
                            blocked = True
                            source_errors.append(f"{url}: odpowiedź blokady")
                            continue
                        source_rows.extend(parse_direct_listing(html, source))
                    except Exception as exc:
                        source_errors.append(f"{url}: {type(exc).__name__}: {exc}")
            unique: dict[tuple[str, str, str], dict] = {}
            for row in source_rows:
                unique[(row.get("event", ""), row.get("market", ""), row.get("event_url", ""))] = row
            return source, list(unique.values()), source_errors, bytes_total, blocked

        ordered = tuple(sorted(DIRECT_SOURCES, key=lambda s: s.priority))
        results = await asyncio.gather(*(one(source) for source in ordered))

    for source, rows, source_errors, bytes_total, blocked in results:
        all_rows.extend(rows)
        errors.extend(f"{source.bookmaker}: {msg}" for msg in source_errors)
        stats[source.bookmaker] = {
            "markets": len(rows),
            "html_bytes": bytes_total,
            "blocked": bool(blocked),
            "ok": bool(rows) or (bytes_total > 0 and not source_errors),
            "mode": "public-http-v29",
        }

    return all_rows, errors, {"enabled": True, "sources": stats, "markets": len(all_rows)}
