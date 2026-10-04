from __future__ import annotations
import httpx

def render(arb):
    lines=[f'🚨 SUREBET +{arb.profit_pct:.2f}%',f'{arb.sport} • {arb.market}',f'📌 {arb.event}','',f'💰 Stawka: {arb.bankroll:.2f} zł',f'💵 Wypłata min.: {arb.guaranteed_payout:.2f} zł',f'📈 Zysk min.: {arb.guaranteed_profit:.2f} zł','']
    for leg in arb.legs: lines.append(f'• {leg.bookmaker}: {leg.selection} @ {leg.odds:.2f} → {leg.stake:.2f} zł')
    lines += ['', '⚠️ Sprawdź kursy bezpośrednio przed zawarciem obu zakładów.']
    return '\n'.join(lines)

async def send(token,chat,text):
    async with httpx.AsyncClient(timeout=15) as c:
        r=await c.post(f'https://api.telegram.org/bot{token}/sendMessage',json={'chat_id':chat,'text':text})
        if r.status_code>=400: raise RuntimeError(r.text[:500])

async def discover(token):
    async with httpx.AsyncClient(timeout=10) as c:
        r=await c.get(f'https://api.telegram.org/bot{token}/getUpdates')
        r.raise_for_status(); data=r.json()
    chats=[]
    for u in data.get('result',[]):
        msg=u.get('message') or u.get('channel_post')
        if msg and msg.get('chat'): chats.append(msg['chat'])
    return chats[-1] if chats else None
