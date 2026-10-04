from __future__ import annotations

import html
import httpx


def _h(value) -> str:
    return html.escape(str(value or ""), quote=True)


def render(arb) -> str:
    lines = [
        f"<b>🚨 NOWY SUREBET +{arb.profit_pct:.2f}%</b>",
        f"{_h(arb.sport)} • {_h(arb.market)}",
        f"📌 <b>{_h(arb.event)}</b>",
        "",
        f"💰 Budżet: <b>{arb.bankroll:.2f} zł</b>",
        f"💵 Wypłata min.: <b>{arb.guaranteed_payout:.2f} zł</b>",
        f"📈 Zysk min.: <b>+{arb.guaranteed_profit:.2f} zł</b>",
        "",
    ]

    for leg in arb.legs:
        book = _h(leg.bookmaker)
        url = leg.bookmaker_url or leg.source_url
        if url:
            book = f'<a href="{_h(url)}">{book}</a>'
        lines.append(
            f"• {book}: {_h(leg.selection)} @ <b>{leg.odds:.2f}</b> → "
            f"<b>{leg.stake:.2f} zł</b>"
        )

    lines += [
        "",
        "⚡ Alert wysłany po potwierdzeniu kursów.",
        "⚠️ Kurs może zmienić się w każdej chwili — sprawdź obie strony przed postawieniem.",
    ]
    return "\n".join(lines)


def buttons(arb) -> dict | None:
    keyboard = []
    seen = set()

    for leg in arb.legs:
        url = leg.bookmaker_url or leg.source_url
        if not url or url in seen:
            continue
        seen.add(url)
        keyboard.append(
            [
                {
                    "text": f"🎯 Otwórz {leg.bookmaker}",
                    "url": url,
                }
            ]
        )

    if arb.event_url and arb.event_url not in seen:
        keyboard.append([{"text": "📊 Porównanie kursów", "url": arb.event_url}])

    return {"inline_keyboard": keyboard} if keyboard else None


async def send(token: str, chat: str, arb) -> None:
    payload = {
        "chat_id": chat,
        "text": render(arb),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    markup = buttons(arb)
    if markup:
        payload["reply_markup"] = markup

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
        )
        if response.status_code >= 400:
            raise RuntimeError(response.text[:500])


async def discover(token):
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"https://api.telegram.org/bot{token}/getUpdates"
        )
        response.raise_for_status()
        data = response.json()

    chats = []
    for update in data.get("result", []):
        message = update.get("message") or update.get("channel_post")
        if message and message.get("chat"):
            chats.append(message["chat"])
    return chats[-1] if chats else None
