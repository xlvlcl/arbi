from __future__ import annotations

import html as htmlmod
import json
import re
import time
from pathlib import Path

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

ROOT = Path(__file__).resolve().parents[2]
DEBUG_DIR = ROOT / "debug"


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
    soup = BeautifulSoup(page_html, "html.parser")
    out = []
    now = time.time()

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header = []
        for tr in rows[:3]:
            cells = [
                clean(x.get_text(" ", strip=True))
                for x in tr.find_all(["th", "td"])
            ]
            if any(x in {"1", "X", "2"} for x in cells) or any(
                "1x2" in x.lower() for x in cells
            ):
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
        self.diagnostics = {}

    async def start(self):
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)

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
            browser_kind = "system-google-chrome"
        except Exception:
            self.browser = await self.pw.chromium.launch(
                headless=self.settings.headless,
                args=launch_args,
            )
            browser_kind = "playwright-chromium"

        context = await self.browser.new_context(
            locale="pl-PL",
            timezone_id="Europe/Warsaw",
            viewport={"width": 1440, "height": 1200},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/154.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.7",
            },
        )

        # Nie zmienia IP runnera. Jedynie upodabnia zachowanie do zwykłej przeglądarki.
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            """
        )

        self.page = await context.new_page()
        self.diagnostics["browser_kind"] = browser_kind

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()

    async def _save_debug(self, label: str):
        assert self.page
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)

        try:
            html = await self.page.content()
        except Exception:
            html = ""

        try:
            body_text = await self.page.locator("body").inner_text(timeout=3000)
        except Exception:
            body_text = ""

        try:
            title = await self.page.title()
        except Exception:
            title = ""

        try:
            await self.page.screenshot(
                path=str(DEBUG_DIR / f"{label}.png"),
                full_page=True,
            )
        except Exception as exc:
            self.diagnostics[f"{label}_screenshot_error"] = str(exc)

        (DEBUG_DIR / f"{label}.html").write_text(
            html,
            encoding="utf-8",
            errors="ignore",
        )
        (DEBUG_DIR / f"{label}.txt").write_text(
            body_text,
            encoding="utf-8",
            errors="ignore",
        )

        soup = BeautifulSoup(html, "html.parser")
        lower = body_text.lower()

        self.diagnostics.update(
            {
                f"{label}_url": self.page.url,
                f"{label}_title": title,
                f"{label}_html_bytes": len(html.encode("utf-8", errors="ignore")),
                f"{label}_body_chars": len(body_text),
                f"{label}_tables": len(soup.find_all("table")),
                f"{label}_rows": len(soup.find_all("tr")),
                f"{label}_links": len(soup.find_all("a")),
                f"{label}_buttons": len(soup.find_all("button")),
                f"{label}_possible_block": any(
                    marker in lower
                    for marker in (
                        "verify you are human",
                        "just a moment",
                        "access denied",
                        "forbidden",
                        "captcha",
                        "cloudflare",
                        "nietypowy ruch",
                        "sprawdź, czy jesteś człowiekiem",
                        "odmowa dostępu",
                    )
                ),
            }
        )

        (DEBUG_DIR / "diagnostics.json").write_text(
            json.dumps(self.diagnostics, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def _click_sport(self, sport: str) -> bool:
        assert self.page

        candidates = [
            self.page.get_by_text(sport, exact=True),
            self.page.get_by_text(sport, exact=False),
        ]

        for loc in candidates:
            try:
                count = await loc.count()
                for i in range(min(count, 20)):
                    item = loc.nth(i)
                    try:
                        if await item.is_visible():
                            await item.click(timeout=5000)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue

        return False

    async def _dismiss_cookie_banner(self):
        assert self.page

        for label in (
            "Tylko niezbędne",
            "Tylko niezbędne pliki",
            "Akceptuj niezbędne",
            "Odrzuć opcjonalne",
            "Akceptuję",
            "Akceptuj",
            "Zgadzam się",
        ):
            try:
                loc = self.page.get_by_text(label, exact=True)
                if await loc.count() and await loc.first.is_visible():
                    await loc.first.click(timeout=1800)
                    await self.page.wait_for_timeout(500)
                    return
            except Exception:
                pass

    async def scan_all(self, sports):
        assert self.page

        all_events = []
        errors = []

        try:
            response = await self.page.goto(
                self.settings.source_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            self.diagnostics["goto_status"] = (
                response.status if response is not None else None
            )

            # Na CI strona może doładowywać JS dużo wolniej niż lokalnie.
            try:
                await self.page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:
                pass

            await self.page.wait_for_timeout(4500)
            await self._dismiss_cookie_banner()
            await self.page.wait_for_timeout(1200)

            await self._save_debug("landing")

        except Exception as exc:
            errors.append(f"Ładowanie DobryBuk: {type(exc).__name__}: {exc}")
            try:
                await self._save_debug("load_error")
            except Exception:
                pass
            return [], errors

        for index, sport in enumerate(sports):
            try:
                clicked = await self._click_sport(sport)
                if not clicked:
                    errors.append(f"{sport}: nie znaleziono widocznego przycisku/tekstu sportu")
                    continue

                try:
                    await self.page.wait_for_load_state("networkidle", timeout=7000)
                except Exception:
                    pass

                await self.page.wait_for_timeout(1800)

                body = await self.page.content()
                rows = extract_tables(body, sport, self.settings.source_url)

                if not rows:
                    errors.append(f"{sport}: kliknięto, ale parser znalazł 0 wydarzeń")
                else:
                    all_events.extend(rows)

                # Jeden screenshot po pierwszym klikniętym sporcie wystarczy diagnostycznie.
                if index == 0 or (not all_events and index == len(sports) - 1):
                    await self._save_debug(f"sport_{index + 1}")

            except Exception as exc:
                errors.append(f"{sport}: {type(exc).__name__}: {exc}")

        unique = {}
        for event in all_events:
            key = (event["sport"], event["event"], event["market"])
            unique[key] = event

        self.diagnostics["events_found"] = len(unique)
        self.diagnostics["errors"] = errors[-50:]

        try:
            await self._save_debug("final")
        except Exception:
            pass

        return list(unique.values()), errors
