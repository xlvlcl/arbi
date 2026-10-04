from __future__ import annotations

import html as htmlmod
import re
import shutil
import time

from bs4 import BeautifulSoup
from playwright.async_api import Page, async_playwright

SPORTS = [
    "Piłka nożna",
    "Tenis",
    "Koszykówka",
    "Hokej",
    "Piłka ręczna",
    "MMA",
    "Boks",
    "Dart",
    "Żużel",
    "Baseball",
    "Futbol amerykański",
    "Tenis stołowy",
]

BOOKS = {
    "Superbet", "STS", "Fortuna", "Betclic", "Forbet", "LVBet",
    "ETOTO", "eToto", "Betfan", "Fuksiarz", "TotalBet", "Total Bet",
    "Betters", "LeBull", "AdmiralBet", "BetSport", "Betsport",
    "ComeOn", "PZBuk",
}

ODDS_RE = re.compile(r"(?<!\d)(?:[1-9]\d{0,2})(?:[\.,]\d{2})(?!\d)")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


def clean(s: str) -> str:
    s = htmlmod.unescape(s or "")
    return re.sub(r"\s+", " ", s).strip()


def cell_data(td):
    txt = clean(td.get_text(" ", strip=True))
    odds = [float(x.replace(",", ".")) for x in ODDS_RE.findall(txt)]
    books = []
    for img in td.find_all("img"):
        alt = clean(img.get("alt", ""))
        for book in BOOKS:
            if alt.lower() == book.lower() or book.lower() in alt.lower():
                books.append(book)
    return txt, odds, books


def extract_tables(page_html: str, sport: str, source_url: str):
    """
    Parser z pierwszej wersji, która działała lokalnie.
    Czyta widoczne tabele kursów po renderowaniu strony przez Playwright.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    out = []
    now = time.time()

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header = []
        for tr in rows[:3]:
            cells = [clean(x.get_text(" ", strip=True)) for x in tr.find_all(["th", "td"])]
            if any(x in {"1", "X", "2"} for x in cells) or any("1x2" in x.lower() for x in cells):
                header = cells
                break
        if not header:
            continue

        for tr in rows:
            tds = tr.find_all(["td", "th"])
            if len(tds) < 4:
                continue

            cells = [cell_data(td) for td in tds]
            time_text = cells[0][0]
            if not TIME_RE.match(time_text):
                continue

            event = clean(cells[1][0])
            if not event or len(event) < 5:
                continue

            market = "1X2"
            if len(header) >= 4:
                header_tail = [clean(x) for x in header[3:]]
                if header_tail:
                    market = " / ".join(header_tail[:3])

            start = 3
            row_cells = cells[start:]
            labels = header[start:] if len(header) > start else []
            quotes = {}

            for idx, cd in enumerate(row_cells):
                if not cd[1]:
                    continue
                odds = max(cd[1])
                label = labels[idx] if idx < len(labels) else str(idx + 1)
                if label.lower() in {"bonusy", "bonus", ""}:
                    continue
                book = cd[2][0] if cd[2] else "Unknown"
                if book == "Unknown":
                    continue

                quotes.setdefault(label, []).append(
                    {
                        "selection": label,
                        "odds": odds,
                        "bookmaker": book,
                        "observed_at": now,
                        "source_url": source_url,
                    }
                )

            if quotes:
                out.append(
                    {
                        "event": event,
                        "sport": sport,
                        "market": market,
                        "quotes": quotes,
                        "observed_at": now,
                        "source_url": source_url,
                    }
                )

    return out


class DobryBukProvider:
    def __init__(self, settings):
        self.settings = settings
        self.pw = None
        self.browser = None
        self.page: Page | None = None

    async def start(self):
        self.pw = await async_playwright().start()

        # Na GitHub Actions jest zwykle systemowy Google Chrome.
        # Lokalnie próbujemy najpierw Chrome, a potem Playwright Chromium.
        try:
            self.browser = await self.pw.chromium.launch(
                channel="chrome",
                headless=self.settings.headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        except Exception:
            self.browser = await self.pw.chromium.launch(
                headless=self.settings.headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )

        self.page = await self.browser.new_page(
            locale="pl-PL",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/154.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 1200},
        )

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()

    async def _click_sport(self, sport: str) -> bool:
        assert self.page
        try:
            loc = self.page.get_by_text(sport, exact=True)
            count = await loc.count()
            for i in range(count):
                try:
                    item = loc.nth(i)
                    if await item.is_visible():
                        await item.click(timeout=3500)
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    async def _dismiss_cookie_banner(self):
        assert self.page
        for label in (
            "Tylko niezbędne",
            "Tylko niezbędne pliki",
            "Akceptuj niezbędne",
            "Odrzuć opcjonalne",
        ):
            try:
                loc = self.page.get_by_text(label, exact=True)
                if await loc.count() and await loc.first.is_visible():
                    await loc.first.click(timeout=1500)
                    return
            except Exception:
                pass

    async def scan_all(self, sports):
        assert self.page
        all_events = []
        errors = []

        try:
            await self.page.goto(
                self.settings.source_url,
                wait_until="domcontentloaded",
                timeout=45000,
            )
            await self.page.wait_for_timeout(1600)
            await self._dismiss_cookie_banner()
        except Exception as exc:
            return [], [f"Ładowanie DobryBuk: {exc}"]

        for sport in sports:
            try:
                clicked = await self._click_sport(sport)
                if not clicked:
                    continue

                await self.page.wait_for_timeout(1000)
                body = await self.page.content()
                rows = extract_tables(body, sport, self.settings.source_url)
                all_events.extend(rows)
            except Exception as exc:
                errors.append(f"{sport}: {exc}")

        # Usuń duplikaty, które mogą pojawić się przy ponownym renderowaniu.
        unique = {}
        for event in all_events:
            key = (event["sport"], event["event"], event["market"])
            unique[key] = event

        return list(unique.values()), errors
