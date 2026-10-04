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
    "kart",
    "gol",
    "strzeli",
    "scorer",
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
)


def clean(value: str) -> str:
    value = htmlmod.unescape(value or "")
    return re.sub(r"\s+", " ", value).strip()


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
        event = clean(a.get_text(" ", strip=True))
        if not event:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                event = clean(cells[1].get_text(" ", strip=True))
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
        event = clean(a.get_text(" ", strip=True))
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

    def _looks_like_market_label(self, label: str) -> bool:
        low = normalize_label(label).lower()
        if not low or low in NAV_SKIP or len(low) > 80:
            return False
        if TIME_RE.fullmatch(low):
            return False
        if any(hint in low for hint in MARKET_HINTS):
            return True
        # Common direct labels on the current source.
        if re.fullmatch(r"h\s*[+-]\s*\d+(?:[\.,]\d+)?", low):
            return True
        return False

    async def _market_buttons_on(self, page: Page) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        try:
            buttons = await page.get_by_role("button").all()
        except Exception:
            buttons = []

        for button in buttons:
            try:
                if not await button.is_visible():
                    continue
                text = normalize_label(await button.inner_text())
            except Exception:
                continue
            key = text.lower()
            if key in seen or not self._looks_like_market_label(text):
                continue
            seen.add(key)
            names.append(text)

        # 1x2 is the default market and can sometimes be rendered as selected text, not a button.
        if not any(x.lower() == "1x2" for x in names):
            names.insert(0, "1x2")
        return names

    async def _click_market_on(self, page: Page, market: str) -> bool:
        target = normalize_label(market).lower().replace(" ", "")
        try:
            buttons = await page.get_by_role("button").all()
        except Exception:
            buttons = []

        for button in buttons:
            try:
                if not await button.is_visible():
                    continue
                text = normalize_label(await button.inner_text())
                if text.lower().replace(" ", "") != target:
                    continue
                await button.scroll_into_view_if_needed(timeout=1000)
                await button.click(timeout=2500)
                await page.wait_for_timeout(650)
                return True
            except Exception:
                continue
        return market.strip().lower() == "1x2"

    async def _scan_event_markets(self, page: Page, event: dict) -> tuple[list[dict], list[str]]:
        event_url = event.get("event_url", "")
        if not event_url:
            return [], ["brak event_url"]

        errors: list[str] = []
        try:
            await page.goto(event_url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(850)
            await self._dismiss_cookie_banner(page)
        except Exception as exc:
            return [], [f"ładowanie wydarzenia: {type(exc).__name__}: {exc}"]

        market_names = await self._market_buttons_on(page)
        max_markets = max(1, int(getattr(self.settings, "max_markets_per_event", 40)))
        market_names = market_names[:max_markets]

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
