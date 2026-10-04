from __future__ import annotations

import asyncio
import html as htmlmod
import json
import re
import shutil
import time
from pathlib import Path
from collections import defaultdict
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, Page, async_playwright

SPORTS_FALLBACK = [
    "Piłka nożna",
    "Tenis",
    "Koszykówka",
    "Siatkówka",
    "Hokej",
    "Piłka ręczna",
    "MMA",
    "Boks",
    "Dart",
    "Żużel",
    "Baseball",
    "Futbol amerykański",
    "Tenis stołowy",
    "Snooker",
    "Rugby",
    "Futsal",
    "Badminton",
    "Golf",
    "Kolarstwo",
    "Formuła 1",
    "Motorsport",
    "Esport",
    "Biathlon",
    "Narciarstwo",
    "Skoki narciarskie",
    "Hokej na trawie",
    "Piłka wodna",
    "Krykiet",
]

BOOKS = {
    "Superbet",
    "STS",
    "Fortuna",
    "eFortuna",
    "Betclic",
    "Forbet",
    "LVBet",
    "ETOTO",
    "eToto",
    "Etoto",
    "BETFAN",
    "Betfan",
    "Fuksiarz",
    "TotalBet",
    "Total Bet",
    "Totalbet",
    "Betters",
    "LeBull",
    "AdmiralBet",
    "BetSport",
    "Betsport",
    "ComeOn",
    "PZBuk",
}

ALIASES = {
    "etoto": "ETOTO",
    "total bet": "TotalBet",
    "totalbet": "TotalBet",
    "betsport": "BetSport",
    "efortuna": "Fortuna",
    "fortuna": "Fortuna",
    "betfan": "Betfan",
}

PCT_RE = re.compile(r"(?<!\d)\d{1,3}(?:[\.,]\d+)?\s*%")
ODDS_RE = re.compile(r"(?<!\d)(?:[1-9]\d{0,2})(?:[\.,]\d{2})(?!\d)")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
EVENT_PATH_RE = re.compile(r"/kursy/mecz/")

NAV_SKIP = {
    "szczegóły",
    "szczegoly",
    "składy",
    "sklady",
    "h2h",
    "tabela",
    "kursy",
    "więcej",
    "wiecej",
    "all",
    "nadchodzące",
    "na żywo",
    "zakończone",
    "wszystkie",
}


ROOT = Path(__file__).resolve().parents[2]
DEBUG_DIR = ROOT / "debug"

MARKET_HINTS = (
    "1x2",
    "1x / x2",
    "u/o",
    "over",
    "under",
    "bts",
    "btts",
    "dnb",
    "handicap",
    "h -",
    "h +",
    "strza",
    "celne",
    "faule",
    "spalone",
    "ofsajd",
    "rożne",
    "rozne",
    "korn",
    "kart",
    "gol",
    "gole",
    "strzeli",
    "scorer",
    "pierwszy",
    "ostatni",
    "dokładny wynik",
    "dokladny wynik",
    "correct score",
    "połowa",
    "polowa",
    "half",
    "ht/ft",
    "ht-ft",
    "punkty",
    "points",
    "zbiórki",
    "zbiorki",
    "rebounds",
    "asysty",
    "assists",
    "asy",
    "aces",
    "set",
    "gemy",
    "games",
    "winner",
    "zwycięzca",
    "zwyciezca",
    "kwalifik",
    "awans",
    "tak/nie",
    "yes/no",
    "clean sheet",
    "czyste konto",
    "rzut karny",
    "penalty",
    "odd/even",
    "parzyst",
    "nieparzyst",
    "metoda zwycięstwa",
    "sposób zwycięstwa",
    "method of victory",
    "wynik setów",
    "set score",
    "liczba setów",
    "liczba gemów",
    "team total",
    "suma drużyny",
    "suma druzyny",
    "player total",
    "zawodnik",
    "gracz",
    "kwarta",
    "quarter",
    "okres",
    "period",
    "inning",
    "mapa",
    "map ",
    "round",
    "runda",
)


def clean(value: str) -> str:
    value = htmlmod.unescape(value or "")
    return re.sub(r"\s+", " ", value).strip()


EVENT_NOISE_RE = re.compile(
    r"\s+(?:RYNEK|KURS|ŚREDNIA|SREDNIA|DO\s+KUPONU|IDŹ\s+DO|IDZ\s+DO)\b.*$",
    re.I,
)


def clean_event_name(value: str) -> str:
    """Remove promo/value text accidentally captured inside an event anchor."""
    value = clean(value)
    value = EVENT_NOISE_RE.sub("", value).strip(" ·|-")
    return clean(value)


def _strip_leading_icon(value: str) -> str:
    # Sport labels on DobryBuk are usually prefixed by an emoji/icon.
    value = clean(value)
    return re.sub(
        r"^[^0-9A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+",
        "",
        value,
    ).strip()


def discover_sports_from_text(body_text: str) -> list[str]:
    """Read the complete sport filter dynamically from the page.

    We intentionally do not keep the scanner tied to a hard-coded sport list.
    Everything visible between the 'Sporty' and 'Status zdarzeń' headings is
    treated as a sport filter. A fallback list is only used if the page layout
    changes and this automatic discovery returns nothing.
    """
    text = (body_text or "").replace("\r", "")
    start = text.lower().find("sporty")
    if start < 0:
        return []
    end = text.lower().find("status zdarzeń", start)
    if end < 0:
        end = text.lower().find("status zdarzen", start)
    if end < 0:
        return []

    segment = text[start + len("sporty"):end]
    out: list[str] = []
    seen: set[str] = set()
    for raw in segment.split("\n"):
        label = _strip_leading_icon(raw)
        if not label or len(label) > 48:
            continue
        low = label.lower()
        if low in {"sporty", "wszystkie", "all"}:
            continue
        # Reject headings/control fragments that are not sport names.
        if any(token in low for token in ("ulubione ligi", "zaloguj", "status zdarzeń")):
            continue
        if low not in seen:
            seen.add(low)
            out.append(label)
    return out


def normalize_label(value: str) -> str:
    value = clean(value).replace("↑", "").replace("↓", "")
    value = PCT_RE.sub(" ", value)
    return clean(value)


def canonical_book(name: str) -> str:
    value = clean(name)
    return ALIASES.get(value.lower(), value)


def odds_from_text(value: str) -> list[float]:
    # Detail rows often contain an odds value and a probability, e.g. 4.40 21.1%.
    # Remove probabilities before extracting decimals so 21.1 is never treated as odds.
    value = PCT_RE.sub(" ", clean(value))
    out: list[float] = []
    for token in ODDS_RE.findall(value):
        try:
            number = float(token.replace(",", "."))
        except ValueError:
            continue
        if 1.0 < number <= 1000:
            out.append(number)
    return out


def _absolute(url: str, base: str = "https://dobrybuk.pl") -> str:
    url = clean(url)
    return urljoin(base, url) if url else ""


def _known_book(name: str) -> str | None:
    low = clean(name).lower()
    if not low:
        return None
    for candidate in BOOKS:
        if candidate.lower() == low or candidate.lower() in low:
            return canonical_book(candidate)
    return None


def _book_from_cell(td) -> tuple[str | None, str]:
    # Prefer visible text / direct bookmaker link on detail tables.
    link = td.find("a", href=True)
    link_url = _absolute(link.get("href", "")) if link else ""

    candidates = [clean(td.get_text(" ", strip=True))]
    if link:
        candidates.append(clean(link.get_text(" ", strip=True)))
        candidates.extend(clean(img.get("alt", "")) for img in link.find_all("img"))
    candidates.extend(clean(img.get("alt", "")) for img in td.find_all("img"))

    for candidate in candidates:
        found = _known_book(candidate)
        if found:
            return found, link_url
    return None, link_url


def discover_events_from_html(page_html: str, sport: str, source_url: str) -> list[dict]:
    """Discover every event link visible for the currently selected sport.

    Listing odds are deliberately NOT used for arbitration. They are only a discovery layer;
    real surebet calculation uses the complete bookmaker table from each event detail page.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    events: list[dict] = []
    seen: set[str] = set()

    # Prefer rows because they keep the event name clean and avoid duplicate mobile/desktop cards.
    for row in soup.find_all("tr"):
        links = [a for a in row.find_all("a", href=True) if EVENT_PATH_RE.search(a.get("href", ""))]
        if not links:
            continue
        a = links[0]
        url = _absolute(a.get("href", ""), source_url)
        if not url or url in seen:
            continue
        event = clean_event_name(a.get_text(" ", strip=True))
        if not event:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                event = clean_event_name(cells[1].get_text(" ", strip=True))
        if len(event) < 3:
            continue
        seen.add(url)
        events.append({"event": event, "sport": sport, "event_url": url})

    # Fallback for card layouts / responsive markup.
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not EVENT_PATH_RE.search(href):
            continue
        url = _absolute(href, source_url)
        if not url or url in seen:
            continue
        event = clean_event_name(a.get_text(" ", strip=True))
        if len(event) < 3:
            continue
        seen.add(url)
        events.append({"event": event, "sport": sport, "event_url": url})

    return events


def extract_detail_market(
    page_html: str,
    event: str,
    sport: str,
    market: str,
    event_url: str,
) -> dict | None:
    """Parse all bookmaker quotes for one selected market on an event page."""
    soup = BeautifulSoup(page_html, "html.parser")
    now = time.time()

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header: list[str] = []
        header_idx = -1
        for idx, row in enumerate(rows[:10]):
            cells = [normalize_label(x.get_text(" ", strip=True)) for x in row.find_all(["th", "td"])]
            if len(cells) >= 3 and cells[0].strip().lower() in {"bukmacher", "bookmaker"}:
                header = cells
                header_idx = idx
                break

        if not header:
            continue

        labels = [x for x in header[1:] if x]
        if len(labels) < 2:
            continue

        quotes: dict[str, list[dict]] = defaultdict(list)
        for row in rows[header_idx + 1 :]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            bookmaker, bookmaker_url = _book_from_cell(cells[0])
            if not bookmaker:
                continue

            for idx, cell in enumerate(cells[1:]):
                if idx >= len(labels):
                    break
                values = odds_from_text(cell.get_text(" ", strip=True))
                if not values:
                    continue
                selection = normalize_label(labels[idx])
                if not selection:
                    continue
                # There should normally be one odds value after percentages are removed.
                # max() is safe for occasional duplicated mobile/desktop fragments.
                odds = max(values)
                quotes[selection].append(
                    {
                        "selection": selection,
                        "odds": odds,
                        "bookmaker": bookmaker,
                        "observed_at": now,
                        "source_url": event_url,
                        "bookmaker_url": bookmaker_url,
                    }
                )

        if len(quotes) >= 2:
            # Remove duplicate bookmaker rows for each outcome, keep their best current quote.
            compact: dict[str, list[dict]] = {}
            for selection, items in quotes.items():
                per_book: dict[str, dict] = {}
                for item in items:
                    old = per_book.get(item["bookmaker"])
                    if old is None or item["odds"] > old["odds"]:
                        per_book[item["bookmaker"]] = item
                compact[selection] = sorted(
                    per_book.values(), key=lambda x: x["odds"], reverse=True
                )
            return {
                "event": event,
                "sport": sport,
                "market": clean(market) or "Rynek",
                "quotes": compact,
                "observed_at": now,
                "source_url": event_url,
                "event_url": event_url,
            }

    return None


def _listing_cell_data(td):
    txt = clean(td.get_text(" ", strip=True))
    odds = odds_from_text(txt)
    books: list[str] = []

    candidates = [clean(img.get("alt", "")) for img in td.find_all("img")]
    candidates.append(txt)
    for candidate in candidates:
        found = _known_book(candidate)
        if found and found not in books:
            books.append(found)

    return txt, odds, books


def extract_listing_tables(page_html: str, sport: str, source_url: str) -> list[dict]:
    """Awaryjny parser tabeli głównej oparty o pierwszą działającą wersję."""
    soup = BeautifulSoup(page_html, "html.parser")
    out: list[dict] = []
    now = time.time()

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header: list[str] = []
        for tr in rows[:5]:
            cells = [
                normalize_label(x.get_text(" ", strip=True))
                for x in tr.find_all(["th", "td"])
            ]
            low = [x.lower() for x in cells]
            if any(x in {"1", "x", "2"} for x in low) or any("1x2" in x for x in low):
                header = cells
                break

        if not header:
            continue

        for tr in rows:
            tds = tr.find_all(["td", "th"])
            if len(tds) < 4:
                continue

            cells = [_listing_cell_data(td) for td in tds]
            if not TIME_RE.match(cells[0][0]):
                continue

            event = clean(cells[1][0])
            if not event or len(event) < 5:
                continue

            event_url = ""
            for a in tds[1].find_all("a", href=True):
                href = a.get("href", "")
                if EVENT_PATH_RE.search(href):
                    event_url = _absolute(href, source_url)
                    break

            start = 3
            row_cells = cells[start:]
            labels = header[start:] if len(header) > start else []
            quotes: dict[str, list[dict]] = defaultdict(list)

            for idx, cell in enumerate(row_cells):
                _, values, books = cell
                if not values:
                    continue

                label = normalize_label(labels[idx]) if idx < len(labels) else str(idx + 1)
                if not label or label.lower() in {"bonus", "bonusy"}:
                    continue

                book = books[0] if books else None
                if not book:
                    continue

                quotes[label].append(
                    {
                        "selection": label,
                        "odds": max(values),
                        "bookmaker": book,
                        "observed_at": now,
                        "source_url": source_url,
                        "bookmaker_url": "",
                        "source_name": "DobryBuk listing fallback",
                    }
                )

            if len(quotes) >= 2:
                out.append(
                    {
                        "event": event,
                        "sport": sport,
                        "market": "1X2",
                        "quotes": dict(quotes),
                        "observed_at": now,
                        "source_url": source_url,
                        "event_url": event_url,
                        "source_name": "DobryBuk listing fallback",
                        "source_names": ["DobryBuk listing fallback"],
                    }
                )

    return out


def extract_listing_market(
    page_html: str,
    sport: str,
    market: str,
    source_url: str,
) -> list[dict]:
    """Parse best visible quotes from the main comparison listing for ANY selected market.

    This layer is used for very broad candidate hunting across dates/sports.
    A candidate is never alerted from this alone: it is re-opened on the event page
    and confirmed from the full bookmaker table first.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    now = time.time()
    out: list[dict] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header = []
        header_idx = -1
        event_idx = -1

        for idx, tr in enumerate(rows[:8]):
            cells = [normalize_label(x.get_text(" ", strip=True)) for x in tr.find_all(["th", "td"])]
            lows = [x.lower() for x in cells]
            try:
                possible_event_idx = next(i for i, x in enumerate(lows) if "zdarzenie" in x)
            except StopIteration:
                possible_event_idx = -1

            if possible_event_idx >= 0 and len(cells) >= possible_event_idx + 3:
                header = cells
                header_idx = idx
                event_idx = possible_event_idx
                break

        if not header or event_idx < 0:
            continue

        # columns after "Zdarzenie", excluding bonus/action columns
        selection_cols: list[tuple[int, str]] = []
        for idx in range(event_idx + 1, len(header)):
            label = normalize_label(header[idx])
            low = label.lower()
            if not label or low in {"bonus", "bonusy"}:
                continue
            if low in {"", "więcej", "wiecej"}:
                continue
            selection_cols.append((idx, label))

        if len(selection_cols) < 2:
            continue

        for tr in rows[header_idx + 1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) <= event_idx:
                continue

            # Event URL/name
            event_cell = cells[event_idx]
            event_url = ""
            event = clean_event_name(event_cell.get_text(" ", strip=True))
            for a in event_cell.find_all("a", href=True):
                href = a.get("href", "")
                if EVENT_PATH_RE.search(href):
                    event_url = _absolute(href, source_url)
                    event = clean_event_name(a.get_text(" ", strip=True)) or event
                    break

            if not event_url or len(event) < 3:
                continue

            quotes: dict[str, list[dict]] = defaultdict(list)
            for col_idx, selection in selection_cols:
                if col_idx >= len(cells):
                    continue
                _, values, books = _listing_cell_data(cells[col_idx])
                if not values or not books:
                    continue
                odds = max(values)
                book = books[0]
                quotes[selection].append(
                    {
                        "selection": selection,
                        "odds": odds,
                        "bookmaker": book,
                        "observed_at": now,
                        "source_url": event_url,
                        "bookmaker_url": "",
                        "source_name": "DobryBuk broad listing",
                    }
                )

            if len(quotes) >= 2:
                out.append(
                    {
                        "event": event,
                        "sport": sport,
                        "market": clean(market) or "Rynek",
                        "quotes": dict(quotes),
                        "observed_at": now,
                        "source_url": event_url,
                        "event_url": event_url,
                        "source_name": "DobryBuk broad listing",
                        "source_names": ["DobryBuk broad listing"],
                    }
                )

    return out


class DobryBukProvider:
    def __init__(self, settings):
        self.settings = settings
        self.pw = None
        self.browser = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.discovered_sports: list[str] = []

    async def start(self):
        self.pw = await async_playwright().start()
        launch_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--lang=pl-PL",
        ]

        try:
            self.browser = await self.pw.chromium.launch(
                channel="chrome",
                headless=self.settings.headless,
                args=launch_args,
            )
        except Exception:
            self.browser = await self.pw.chromium.launch(
                headless=self.settings.headless,
                args=launch_args,
            )

        self.context = await self.browser.new_context(
            locale="pl-PL",
            timezone_id="Europe/Warsaw",
            viewport={"width": 1440, "height": 1100},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/154.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "pl-PL,pl;q=0.9,en;q=0.6"},
        )
        await self.context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )

        # Images/fonts/media are irrelevant for parsing and are the biggest cost on hundreds of pages.
        async def route_handler(route):
            if route.request.resource_type in {"image", "font", "media"}:
                await route.abort()
            else:
                await route.continue_()

        await self.context.route("**/*", route_handler)
        self.page = await self.context.new_page()

    async def stop(self):
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        if self.pw:
            try:
                await self.pw.stop()
            except Exception:
                pass

    async def _dismiss_cookie_banner(self, page: Page):
        for label in (
            "Tylko niezbędne",
            "Tylko niezbędne pliki",
            "Akceptuj niezbędne",
            "Odrzuć opcjonalne",
            "Akceptuję",
            "Akceptuj",
        ):
            try:
                loc = page.get_by_text(label, exact=True)
                if await loc.count() and await loc.first.is_visible():
                    await loc.first.click(timeout=1600)
                    await page.wait_for_timeout(650)
                    return
            except Exception:
                pass

    async def _click_sport(self, sport: str) -> bool:
        assert self.page
        locators = [
            self.page.get_by_role("button", name=sport, exact=True),
            self.page.get_by_text(sport, exact=True),
        ]
        for locator in locators:
            try:
                count = await locator.count()
                for i in range(min(count, 30)):
                    item = locator.nth(i)
                    try:
                        if not await item.is_visible():
                            continue
                        await item.scroll_into_view_if_needed(timeout=1200)
                        await item.click(timeout=3500)
                        await self.page.wait_for_timeout(700)
                        return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False

    async def _save_discovery_debug(self, label: str):
        """Save what GitHub's browser actually sees without changing page output."""
        assert self.page
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            html = await self.page.content()
        except Exception:
            html = ""
        try:
            text = await self.page.locator("body").inner_text(timeout=4000)
        except Exception:
            text = ""
        try:
            title = await self.page.title()
        except Exception:
            title = ""
        try:
            hrefs = await self.page.locator('a[href*="/kursy/mecz/"]').count()
        except Exception:
            hrefs = -1
        info = {
            "url": self.page.url,
            "title": title,
            "html_bytes": len(html.encode("utf-8", errors="ignore")),
            "body_chars": len(text),
            "event_link_count": hrefs,
            "discovered_sports": self.discovered_sports,
        }
        try:
            await self.page.screenshot(path=str(DEBUG_DIR / f"{label}.png"), full_page=True)
        except Exception as exc:
            info["screenshot_error"] = str(exc)
        (DEBUG_DIR / f"{label}.html").write_text(html, encoding="utf-8", errors="ignore")
        (DEBUG_DIR / f"{label}.txt").write_text(text, encoding="utf-8", errors="ignore")
        (DEBUG_DIR / "discovery.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    async def _collect_event_links(self, sport: str) -> list[dict]:
        """Collect event links directly from the live DOM, with HTML fallback.

        The previous v12 only parsed page.content() immediately after a sport click.
        On GitHub Actions the table often updates asynchronously, so that snapshot could
        contain zero event links even though the rendered page later had them.
        """
        assert self.page
        events: list[dict] = []
        seen: set[str] = set()

        # Wait for either event anchors or table rows to appear. No hard failure: the
        # source can legitimately have no matches for one sport on a given day.
        try:
            await self.page.wait_for_selector(
                'a[href*="/kursy/mecz/"], table tr', timeout=9000
            )
        except Exception:
            pass
        await self.page.wait_for_timeout(1300)

        # Most reliable path: read hrefs from the browser DOM, not from a too-early HTML snapshot.
        loc = self.page.locator('a[href*="/kursy/mecz/"]')
        try:
            count = min(await loc.count(), 1200)
        except Exception:
            count = 0

        for i in range(count):
            a = loc.nth(i)
            try:
                href = await a.get_attribute("href")
                if not href:
                    continue
                url = _absolute(href, self.settings.source_url)
                if not url or url in seen:
                    continue
                text = clean(await a.inner_text(timeout=1000))
                if len(text) < 3:
                    # Some links wrap images/teams and expose poor innerText; use parent row text.
                    try:
                        row = a.locator("xpath=ancestor::tr[1]")
                        row_text = clean(await row.inner_text(timeout=1000))
                        # Remove leading time; leave the event label reasonably readable.
                        row_text = re.sub(r"^\\d{1,2}:\\d{2}\\s+", "", row_text)
                        text = row_text[:180]
                    except Exception:
                        pass
                if len(text) < 3:
                    # Last resort: derive readable name from slug.
                    slug = url.rstrip("/").split("/")[-1]
                    slug = re.sub(r"-\\d{4}-\\d{2}-\\d{2}-\\d+$", "", slug)
                    text = clean(slug.replace("-vs-", " – ").replace("-", " ")).title()
                seen.add(url)
                events.append({"event": text, "sport": sport, "event_url": url})
            except Exception:
                continue

        # Fallback to BeautifulSoup if the DOM locator path unexpectedly returns nothing.
        if not events:
            try:
                html = await self.page.content()
                for item in discover_events_from_html(html, sport, self.settings.source_url):
                    url = item.get("event_url", "")
                    if url and url not in seen:
                        seen.add(url)
                        events.append(item)
            except Exception:
                pass

        return events

    async def discover_events(self, sports: list[str]) -> tuple[list[dict], list[str]]:
        assert self.page
        errors: list[str] = []
        discovered: dict[str, dict] = {}

        try:
            await self.page.goto(
                self.settings.source_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            try:
                await self.page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass
            # The known-good diagnostic version needed a longer settle time on GitHub CI.
            await self.page.wait_for_timeout(4200)
            await self._dismiss_cookie_banner(self.page)
            await self.page.wait_for_timeout(900)
        except Exception as exc:
            return [], [f"Ładowanie DobryBuk: {type(exc).__name__}: {exc}"]

        try:
            body_text = await self.page.locator("body").inner_text(timeout=6000)
        except Exception:
            body_text = ""

        auto_sports = discover_sports_from_text(body_text)
        if auto_sports:
            sports_to_scan = auto_sports
        else:
            sports_to_scan = list(dict.fromkeys((sports or []) + SPORTS_FALLBACK))

        self.discovered_sports = sports_to_scan

        for sport in sports_to_scan:
            try:
                clicked = await self._click_sport(sport)
                if not clicked:
                    # If the current default sport is already selected, its text can be
                    # non-clickable. Still try collecting the currently visible table.
                    current = await self._collect_event_links(sport)
                    if current:
                        for event in current:
                            discovered.setdefault(event["event_url"], event)
                        continue
                    errors.append(f"{sport}: nie znaleziono filtra sportu")
                    continue

                try:
                    await self.page.wait_for_load_state("networkidle", timeout=6500)
                except Exception:
                    pass
                # v12 used 250 ms here; on GitHub this was too short and caused 0 events.
                await self.page.wait_for_timeout(2400)

                events = await self._collect_event_links(sport)
                if not events:
                    errors.append(f"{sport}: 0 linków wydarzeń po odczekaniu")
                for event in events:
                    discovered.setdefault(event["event_url"], event)
            except Exception as exc:
                errors.append(f"{sport}: {type(exc).__name__}: {exc}")

        if not discovered:
            try:
                await self._save_discovery_debug("zero_events")
            except Exception as exc:
                errors.append(f"Debug: {type(exc).__name__}: {exc}")

        return list(discovered.values()), errors

    async def scan_listing_fallback(
        self,
        sports: list[str] | None = None,
    ) -> tuple[list[dict], list[str]]:
        """Fallback tabeli głównej, żeby chwilowy błąd detail-pages nie wyczyścił strony."""
        assert self.page
        errors: list[str] = []
        rows: list[dict] = []

        try:
            await self.page.goto(
                self.settings.source_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            try:
                await self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            await self.page.wait_for_timeout(2800)
            await self._dismiss_cookie_banner(self.page)
        except Exception as exc:
            return [], [f"Fallback listing - ładowanie: {type(exc).__name__}: {exc}"]

        try:
            body_text = await self.page.locator("body").inner_text(timeout=5000)
        except Exception:
            body_text = ""

        auto = discover_sports_from_text(body_text)
        sports_to_scan = auto or list(dict.fromkeys((sports or []) + SPORTS_FALLBACK))
        if not self.discovered_sports:
            self.discovered_sports = sports_to_scan

        for sport in sports_to_scan:
            try:
                await self._click_sport(sport)
                await self.page.wait_for_timeout(1400)
                html = await self.page.content()
                rows.extend(extract_listing_tables(html, sport, self.settings.source_url))
            except Exception as exc:
                errors.append(f"Fallback {sport}: {type(exc).__name__}: {exc}")

        unique: dict[tuple[str, str, str], dict] = {}
        for row in rows:
            key = (
                clean(row.get("sport", "")).lower(),
                clean(row.get("event", "")).lower(),
                clean(row.get("market", "")).lower(),
            )
            unique.setdefault(key, row)

        return list(unique.values()), errors

    async def _click_text_on(self, page: Page, text: str, exact: bool = True) -> bool:
        locators = [
            page.get_by_role("button", name=text, exact=exact),
            page.get_by_text(text, exact=exact),
        ]
        for locator in locators:
            try:
                count = min(await locator.count(), 20)
            except Exception:
                count = 0
            for i in range(count):
                item = locator.nth(i)
                try:
                    if not await item.is_visible():
                        continue
                    await item.scroll_into_view_if_needed(timeout=1200)
                    await item.click(timeout=3000)
                    await page.wait_for_timeout(450)
                    return True
                except Exception:
                    continue
        return False

    async def _market_group_labels(self, page: Page) -> list[str]:
        """Find the UI control group that contains the 1x2 market button.

        This is deliberately structural, not a fixed whitelist. If DobryBuk adds
        a new market beside 1x2 tomorrow, the scanner can see it automatically.
        """
        script = r"""
        () => {
          const norm = s => (s || "").replace(/\s+/g, " ").trim();
          const visible = el => {
            const st = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return st.display !== "none" && st.visibility !== "hidden" && r.width > 0 && r.height > 0;
          };
          const controls = [...document.querySelectorAll('button,[role="button"],[data-market]')]
            .filter(visible)
            .map(el => ({el, text:norm(el.innerText || el.textContent)}))
            .filter(x => x.text && x.text.length <= 100);

          const seed = controls.find(x => x.text.toLowerCase().replace(/\s/g,"") === "1x2");
          if (!seed) return [];

          let node = seed.el.parentElement;
          for (let depth = 0; node && depth < 7; depth++, node = node.parentElement) {
            const inside = [...node.querySelectorAll('button,[role="button"],[data-market]')]
              .filter(visible)
              .map(el => norm(el.innerText || el.textContent))
              .filter(t => t && t.length <= 100);
            const uniq = [...new Set(inside)];
            const hasSeed = uniq.some(t => t.toLowerCase().replace(/\s/g,"") === "1x2");
            if (hasSeed && uniq.length >= 4 && uniq.length <= 80) return uniq;
          }
          return [];
        }
        """
        try:
            labels = await page.evaluate(script)
            if isinstance(labels, list):
                return [normalize_label(str(x)) for x in labels if normalize_label(str(x))]
        except Exception:
            pass
        return []

    async def _activate_upcoming_all_dates(self, page: Page) -> None:
        # Status
        await self._click_text_on(page, "Nadchodzące", exact=True)

        # Current page exposes a dedicated "All" button above the date strip.
        # It is intentionally best-effort because source wording can change.
        clicked_all = await self._click_text_on(page, "All", exact=True)
        if not clicked_all:
            await self._click_text_on(page, "Wszystkie daty", exact=True)
        await page.wait_for_timeout(650)

    async def _click_sport_on(self, page: Page, sport: str) -> bool:
        locators = [
            page.get_by_role("button", name=sport, exact=True),
            page.get_by_text(sport, exact=True),
        ]
        for locator in locators:
            try:
                count = min(await locator.count(), 30)
            except Exception:
                count = 0
            for i in range(count):
                item = locator.nth(i)
                try:
                    if not await item.is_visible():
                        continue
                    await item.scroll_into_view_if_needed(timeout=1200)
                    await item.click(timeout=3200)
                    await page.wait_for_timeout(650)
                    return True
                except Exception:
                    continue
        return False

    async def discover_priority_events(self) -> tuple[list[dict], list[str]]:
        """Discover events highlighted by DobryBuk value/statistical-value pages.

        We DO NOT trust their value score as our final signal. These events are merely
        moved to the front of our own full-market scan, where our stricter model verifies them.
        """
        assert self.context
        page = await self.context.new_page()
        errors: list[str] = []
        found: dict[str, dict] = {}

        sources = [
            ("https://dobrybuk.pl/valuebety", "Value"),
            ("https://dobrybuk.pl/kursy/statystyczne-value", "Statystyczne Value"),
            ("https://dobrybuk.pl/kursy/statystyczne", "Statystyczne"),
        ]

        try:
            for url, label in sources:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(900)
                    await self._dismiss_cookie_banner(page)

                    loc = page.locator('a[href*="/kursy/mecz/"]')
                    count = min(await loc.count(), 800)
                    for i in range(count):
                        a = loc.nth(i)
                        try:
                            href = await a.get_attribute("href")
                            if not href:
                                continue
                            event_url = _absolute(href, self.settings.source_url)
                            if not event_url:
                                continue
                            text = clean_event_name(await a.inner_text(timeout=700))
                            if len(text) < 3:
                                slug = event_url.split("?")[0].rstrip("/").split("/")[-1]
                                slug = re.sub(r"-\d{4}-\d{2}-\d{2}-\d+$", "", slug)
                                text = clean(slug.replace("-vs-", " – ").replace("-", " ")).title()
                            # Statistical pages are mostly football/tennis; unknown is okay and
                            # later main discovery can overwrite with a more precise sport.
                            sport = "Piłka nożna" if "stat" in event_url.lower() else "Inne"
                            found.setdefault(
                                event_url.split("#")[0],
                                {
                                    "event": text,
                                    "sport": sport,
                                    "event_url": event_url,
                                    "priority_source": label,
                                },
                            )
                        except Exception:
                            continue
                except Exception as exc:
                    errors.append(f"{label}: {type(exc).__name__}: {exc}")
        finally:
            await page.close()

        return list(found.values()), errors

    async def discover_signal_events(self) -> tuple[list[dict], list[str]]:
        """Use public market-movement pages only as a PRIORITY signal.

        A movement is never treated as a bet by itself. We merely scan those event pages sooner.
        """
        assert self.context
        page = await self.context.new_page()
        errors: list[str] = []
        found: dict[str, dict] = {}

        pages = [
            ("https://dobrybuk.pl/kursy/spadki-kursow", "Spadki kursów"),
            ("https://dobrybuk.pl/kursy/spadki-kursow?tab=rises", "Wzrosty kursów"),
        ]

        try:
            for url, label in pages:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(850)
                    await self._dismiss_cookie_banner(page)

                    loc = page.locator('a[href*="/kursy/mecz/"]')
                    count = min(await loc.count(), 600)
                    for i in range(count):
                        a = loc.nth(i)
                        try:
                            href = await a.get_attribute("href")
                            if not href:
                                continue
                            event_url = _absolute(href, self.settings.source_url)
                            if not event_url:
                                continue
                            text = clean_event_name(await a.inner_text(timeout=700))
                            if len(text) < 3:
                                slug = event_url.split("?")[0].rstrip("/").split("/")[-1]
                                slug = re.sub(r"-\d{4}-\d{2}-\d{2}-\d+$", "", slug)
                                text = clean(slug.replace("-vs-", " – ").replace("-", " ")).title()
                            found.setdefault(
                                event_url.split("#")[0],
                                {
                                    "event": text,
                                    "sport": "Inne",
                                    "event_url": event_url,
                                    "priority_source": label,
                                },
                            )
                        except Exception:
                            continue
                except Exception as exc:
                    errors.append(f"{label}: {type(exc).__name__}: {exc}")
        finally:
            await page.close()

        return list(found.values()), errors

    async def scan_broad_listing_markets(
        self,
        max_seconds: int = 105,
    ) -> tuple[list[dict], list[str], dict]:
        """Very broad candidate scan across ALL visible dates/sports/listing markets.

        It reads only the best visible quote for each outcome, which is fast.
        Any surebet candidate found here must still pass the full event-page recheck.
        """
        assert self.context
        page = await self.context.new_page()
        errors: list[str] = []
        rows: list[dict] = []
        started = time.monotonic()
        scanned_pairs = 0

        try:
            await page.goto(self.settings.source_url, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_load_state("networkidle", timeout=7000)
            except Exception:
                pass
            await page.wait_for_timeout(1600)
            await self._dismiss_cookie_banner(page)
            await self._activate_upcoming_all_dates(page)

            try:
                body_text = await page.locator("body").inner_text(timeout=5000)
            except Exception:
                body_text = ""
            sports = discover_sports_from_text(body_text) or self.discovered_sports or SPORTS_FALLBACK

            market_labels = await self._market_group_labels(page)
            market_labels = [
                x for x in market_labels
                if self._looks_like_market_label(x)
                and normalize_label(x).lower() not in NAV_SKIP
            ]
            # Main page currently exposes these; keep deterministic fallback.
            if not market_labels:
                market_labels = [
                    "1x2", "1X / X2 / 12",
                    "U/O 1.5", "U/O 2.5", "U/O 3.5",
                    "BTS", "DNB",
                    "H -2.5", "H -1.5", "H -0.5",
                    "H +0.5", "H +1.5", "H +2.5",
                ]

            for sport in sports:
                if time.monotonic() - started >= max_seconds:
                    break
                await self._click_sport_on(page, sport)
                await page.wait_for_timeout(450)
                await self._activate_upcoming_all_dates(page)

                for market in market_labels:
                    if time.monotonic() - started >= max_seconds:
                        break
                    clicked = await self._click_market_on(page, market)
                    if not clicked:
                        continue
                    await page.wait_for_timeout(260)
                    try:
                        html = await page.content()
                        parsed = extract_listing_market(
                            html,
                            sport,
                            market,
                            self.settings.source_url,
                        )
                        rows.extend(parsed)
                        scanned_pairs += 1
                    except Exception as exc:
                        errors.append(f"{sport}/{market}: {type(exc).__name__}: {exc}")
        finally:
            await page.close()

        unique: dict[tuple[str, str, str], dict] = {}
        for row in rows:
            key = (
                event_key := clean(row.get("event", "")).lower(),
                clean(row.get("sport", "")).lower(),
                clean(row.get("market", "")).lower(),
            )
            if event_key:
                unique.setdefault(key, row)

        return list(unique.values()), errors, {
            "broad_listing_pairs": scanned_pairs,
            "broad_listing_markets": len(unique),
            "broad_listing_elapsed": round(time.monotonic() - started, 2),
        }

    async def _open_odds_tab(self, page: Page) -> bool:
        """Otwórz zakładkę `Kursy` przed szukaniem rynków.

        Na DobryBuk przyciski rynków bywają obecne w DOM, ale ukryte dopóki
        użytkownik nie przejdzie ze `Szczegóły` do `Kursy`. Stary skaner
        filtrował tylko widoczne przyciski, więc kończył z samym 1X2.
        """
        candidates = [
            page.get_by_role("button", name=re.compile(r"^\s*Kursy\s*$", re.I)),
            page.locator('button:has-text("Kursy")'),
            page.locator('[role="button"]:has-text("Kursy")'),
        ]
        for locator in candidates:
            try:
                count = min(await locator.count(), 8)
            except Exception:
                count = 0
            for i in range(count):
                item = locator.nth(i)
                try:
                    if not await item.is_visible():
                        continue
                    await item.scroll_into_view_if_needed(timeout=1500)
                    await item.click(timeout=3500)
                    await page.wait_for_timeout(900)
                    return True
                except Exception:
                    continue

        # Jeśli zakładka jest już aktywna, widoczny przycisk 1x2 wystarczy
        # jako potwierdzenie, że jesteśmy w sekcji kursów.
        try:
            visible_1x2 = page.locator('button:visible').filter(has_text=re.compile(r"^\s*1x2\s*$", re.I))
            if await visible_1x2.count():
                return True
        except Exception:
            pass
        return False

    def _looks_like_market_label(self, label: str) -> bool:
        low = normalize_label(label).lower()
        if not low or low in NAV_SKIP or len(low) > 90:
            return False
        if TIME_RE.fullmatch(low):
            return False
        if low in {"1", "x", "2", "all", "więcej", "wiecej", "kupon"}:
            return False
        if low in {x.lower() for x in SPORTS_FALLBACK}:
            return False
        if any(book.lower() == low for book in BOOKS):
            return False
        if re.fullmatch(r"\d{1,2}[\.:]\d{2}", low):
            return False
        if re.fullmatch(r"\d+(?:[\.,]\d+)?", low):
            return False
        if any(token in low for token in (
            "akceptuj", "cookie", "zaloguj", "rejestr", "ustawienia",
            "historia kursów", "wszystkie kursy bukmacherów",
            "prawdopodobieństwo", "marża", "pozycja w tabeli",
        )):
            return False
        if any(hint in low for hint in MARKET_HINTS):
            return True
        if re.fullmatch(r"h\s*[+-]\s*\d+(?:[\.,]\d+)?", low):
            return True

        # Important v20 behavior: controls found structurally in the SAME market
        # switcher group as 1x2 are allowed even if the source added a brand-new label.
        # This general predicate therefore accepts short descriptive labels containing
        # at least one alphabetic character.
        return len(low) >= 2 and bool(re.search(r"[a-ząćęłńóśźż]", low, re.I))

    async def _market_buttons_on(self, page: Page) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()

        # 1) Best path: every control in the SAME group as the 1x2 switcher.
        for text in await self._market_group_labels(page):
            label = normalize_label(text)
            key = label.lower()
            if key in seen or not self._looks_like_market_label(label):
                continue
            seen.add(key)
            names.append(label)

        # 2) Fallback: scan visible controls + data-market attributes.
        if len(names) <= 1:
            locators = [
                page.locator("button"),
                page.locator('[role="button"]'),
                page.locator("[data-market]"),
            ]
            for locator in locators:
                try:
                    count = min(await locator.count(), 400)
                except Exception:
                    count = 0
                for i in range(count):
                    item = locator.nth(i)
                    try:
                        if not await item.is_visible():
                            continue
                        text = normalize_label(await item.inner_text(timeout=1000))
                    except Exception:
                        continue
                    key = text.lower()
                    if key in seen or not self._looks_like_market_label(text):
                        continue
                    seen.add(key)
                    names.append(text)

        if not any(x.lower().replace(" ", "") == "1x2" for x in names):
            names.insert(0, "1x2")
        return names

    async def _click_market_on(self, page: Page, market: str) -> bool:
        target = normalize_label(market).lower().replace(" ", "")

        if target == "1x2":
            # Rynek domyślny; jeżeli kontrolka jest widoczna, kliknij ją.
            # Gdy jest już aktywny, parsowanie bieżącej tabeli też jest poprawne.
            default_ok = True
        else:
            default_ok = False

        locators = [
            page.locator("button"),
            page.locator('[role="button"]'),
            page.locator("[data-market]"),
        ]
        for locator in locators:
            try:
                count = min(await locator.count(), 300)
            except Exception:
                count = 0

            for i in range(count):
                item = locator.nth(i)
                try:
                    if not await item.is_visible():
                        continue
                    text = normalize_label(await item.inner_text(timeout=1000))
                    if text.lower().replace(" ", "") != target:
                        continue

                    # Zapamiętaj fragment tabeli, aby dać SPA czas na podmianę kursów.
                    try:
                        before = clean(await page.locator("table").last.inner_text(timeout=1200))
                    except Exception:
                        before = ""

                    await item.scroll_into_view_if_needed(timeout=1500)
                    await item.click(timeout=3500)

                    changed = False
                    for _ in range(12):
                        await page.wait_for_timeout(180)
                        try:
                            after = clean(await page.locator("table").last.inner_text(timeout=800))
                        except Exception:
                            after = ""
                        if after and after != before:
                            changed = True
                            break

                    if not changed:
                        await page.wait_for_timeout(650)
                    return True
                except Exception:
                    continue

        return default_ok

    async def _scan_event_markets(self, page: Page, event: dict) -> tuple[list[dict], list[str]]:
        event_url = event.get("event_url", "")
        if not event_url:
            return [], ["brak event_url"]

        errors: list[str] = []
        try:
            await page.goto(event_url, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_load_state("networkidle", timeout=6500)
            except Exception:
                pass
            await page.wait_for_timeout(1200)
            await self._dismiss_cookie_banner(page)
            await self._open_odds_tab(page)

            # Poczekaj, aż sekcja kursów rzeczywiście się pojawi.
            try:
                await page.wait_for_selector("table", timeout=5000)
            except Exception:
                pass
            await page.wait_for_timeout(550)
        except Exception as exc:
            return [], [f"ładowanie wydarzenia: {type(exc).__name__}: {exc}"]

        market_names = await self._market_buttons_on(page)
        max_markets = max(1, int(getattr(self.settings, "max_markets_per_event", 40)))
        market_names = market_names[:max_markets]
        if len(market_names) <= 1:
            errors.append(
                "wykryto tylko 1 rynek na stronie wydarzenia; "
                "prawdopodobnie sekcja kursów nie została w pełni załadowana"
            )

        results: list[dict] = []
        seen_market_keys: set[str] = set()

        for market in market_names:
            key = normalize_label(market).lower()
            if key in seen_market_keys:
                continue
            seen_market_keys.add(key)
            try:
                clicked = await self._click_market_on(page, market)
                if not clicked:
                    errors.append(f"{market}: nie znaleziono przycisku")
                    continue
                html = await page.content()
                parsed = extract_detail_market(
                    html,
                    event["event"],
                    event["sport"],
                    market,
                    event_url,
                )
                if parsed:
                    results.append(parsed)
                else:
                    errors.append(f"{market}: brak pełnej tabeli bukmacherów")
            except Exception as exc:
                errors.append(f"{market}: {type(exc).__name__}: {exc}")

        return results, errors

    async def scan_all_markets(
        self,
        events: list[dict],
        max_events: int = 250,
        max_seconds: int = 330,
        concurrency: int = 4,
    ) -> tuple[list[dict], list[str], dict]:
        """Scan every visible market on event detail pages within one run.

        The source can contain hundreds of events. The time budget prevents a stuck event from
        consuming the entire GitHub job; stats explicitly report whether the run covered all events.
        """
        assert self.page and self.context
        started = time.time()
        selected = events[: max(1, int(max_events))]
        results: list[dict] = []
        errors: list[str] = []
        lock = asyncio.Lock()
        next_index = 0
        scanned_events = 0
        scanned_markets = 0

        pages = [self.page]
        for _ in range(max(1, int(concurrency)) - 1):
            try:
                pages.append(await self.context.new_page())
            except Exception:
                break

        async def worker(page: Page):
            nonlocal next_index, scanned_events, scanned_markets
            while True:
                async with lock:
                    if next_index >= len(selected) or time.time() - started >= max_seconds:
                        return
                    event = selected[next_index]
                    next_index += 1

                details: list[dict] = []
                local_errors: list[str] = []
                try:
                    details, local_errors = await self._scan_event_markets(page, event)
                except Exception as exc:
                    local_errors = [f"{type(exc).__name__}: {exc}"]

                async with lock:
                    results.extend(details)
                    errors.extend(
                        f"{event.get('sport','')} / {event.get('event','')}: {msg}"
                        for msg in local_errors
                    )
                    scanned_events += 1
                    scanned_markets += len(details)

        try:
            await asyncio.gather(*(worker(page) for page in pages))
        finally:
            for page in pages[1:]:
                try:
                    await page.close()
                except Exception:
                    pass

        # A market can occasionally be rendered twice by responsive markup. Dedupe by event URL + market.
        unique: dict[tuple[str, str], dict] = {}
        for item in results:
            key = (item.get("event_url", ""), normalize_label(item.get("market", "")).lower())
            old = unique.get(key)
            if old is None or sum(len(v) for v in item.get("quotes", {}).values()) > sum(
                len(v) for v in old.get("quotes", {}).values()
            ):
                unique[key] = item

        complete = scanned_events >= len(selected) and len(events) <= len(selected)
        stats = {
            "detail_events_scanned": scanned_events,
            "detail_events_total": len(events),
            "markets_scanned": len(unique),
            "exhaustive_complete": complete,
            "budget_seconds": max_seconds,
            "elapsed_seconds": round(time.time() - started, 2),
        }
        return list(unique.values()), errors, stats

    async def scan_specific_markets(
        self,
        targets: list[dict],
        concurrency: int = 2,
        max_seconds: int = 90,
    ) -> tuple[list[dict], list[str]]:
        """Recheck exact candidate event + market combinations before alerting."""
        assert self.page and self.context
        started = time.time()
        unique_targets: dict[tuple[str, str], dict] = {}
        for target in targets:
            url = target.get("event_url", "")
            market = clean(target.get("market", ""))
            if url and market:
                unique_targets[(url, normalize_label(market).lower())] = target
        queue = list(unique_targets.values())

        results: list[dict] = []
        errors: list[str] = []
        lock = asyncio.Lock()
        next_index = 0
        pages = [self.page]
        for _ in range(max(1, int(concurrency)) - 1):
            try:
                pages.append(await self.context.new_page())
            except Exception:
                break

        async def one(page: Page, target: dict):
            url = target["event_url"]
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                await page.wait_for_timeout(700)
                await self._dismiss_cookie_banner(page)
                if not await self._click_market_on(page, target["market"]):
                    return None, "nie znaleziono rynku przy potwierdzeniu"
                html = await page.content()
                return (
                    extract_detail_market(
                        html,
                        target["event"],
                        target["sport"],
                        target["market"],
                        url,
                    ),
                    None,
                )
            except Exception as exc:
                return None, f"{type(exc).__name__}: {exc}"

        async def worker(page: Page):
            nonlocal next_index
            while True:
                async with lock:
                    if next_index >= len(queue) or time.time() - started >= max_seconds:
                        return
                    target = queue[next_index]
                    next_index += 1
                parsed, error = await one(page, target)
                async with lock:
                    if parsed:
                        results.append(parsed)
                    if error:
                        errors.append(f"{target.get('event','')} / {target.get('market','')}: {error}")

        try:
            await asyncio.gather(*(worker(page) for page in pages))
        finally:
            for page in pages[1:]:
                try:
                    await page.close()
                except Exception:
                    pass
        return results, errors

    # Backward-compatible name used by earlier scanner versions.
    async def scan_all(self, sports):
        return await self.discover_events(sports)
