from __future__ import annotations

import html
import httpx

from .models import Surebet


def render(arb: Surebet) -> str:
    lines = [
        f"<b>🚨 SUREBET +{arb.profit_pct:.2f}%</b>",
        f"{html.escape(arb.sport)} • {html.escape(arb.market)}",
        f"📌 <b>{html.escape(arb.event)}</b>",
        "",
        f"💰 Stawka: <b>{arb.bankroll:.2f} zł</b>",
        f"💵 Wypłata min.: <b>{arb.guaranteed_payout:.2f} zł</b>",
        f"📈 Zysk min.: <b>+{arb.guaranteed_profit:.2f} zł</b>",
        "",
    ]
    for leg in arb.legs:
        name = html.escape(leg.bookmaker)
        if leg.bookmaker_url:
            name = f'<a href="{html.escape(leg.bookmaker_url, quote=True)}">{name}</a>'
        lines.append(
            f"• {name}: {html.escape(leg.selection)} @ <b>{leg.odds:.2f}</b> → {leg.stake:.2f} zł"
        )
    lines += ["", "⚠️ Sprawdź oba kursy bezpośrednio przed zawarciem zakładów."]
    return "\n".join(lines)


async def send(token: str, chat_id: str, arb: Surebet) -> None:
    if not token or not chat_id:
        return
    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": render(arb),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
        response.raise_for_status()
