"""Alert state is updated only after a notification service accepts a request."""
import json
import os
import time
import urllib.request


def post_json(url,payload,headers=None):
    body=json.dumps(payload).encode()
    request=urllib.request.Request(url,data=body,method='POST',headers={'Content-Type':'application/json',**(headers or {})})
    with urllib.request.urlopen(request,timeout=7) as response:return json.load(response)


def due(record,profit,now):
    if not record.get('last_sent'):return True
    if now-record.get('last_sent',0)>120*60:return True
    if now-record.get('last_seen',0)>6*60:return True
    return now-record.get('last_sent',0)>60 and profit>=record.get('profit',0)+.15


def send_alerts(opportunities,state,send=post_json,env=None,now=None):
    env=os.environ if env is None else env; now=time.time() if now is None else now
    deadline=time.monotonic()+20
    token=env.get('TELEGRAM_BOT_TOKEN','');chat=env.get('TELEGRAM_CHAT_ID','')
    app_id=env.get('ONESIGNAL_APP_ID','');key=env.get('ONESIGNAL_API_KEY','')
    url=env.get('APP_PUBLIC_URL','https://xlvlcl.github.io/arbi/')
    sent=state.setdefault('sent',{}); accepted=0;errors=[]
    channels={'telegram':bool(token and chat),'push':bool(app_id and key)}
    for opportunity in opportunities:
        record=sent.setdefault(opportunity['id'],{})
        should_send=due(record,opportunity['profit_pct'],now)
        record['last_seen']=now
        if not should_send or not any(channels.values()):continue
        if time.monotonic()>=deadline:
            errors.append('Limit czasu powiadomień — pozostałe alerty spróbują ponownie w następnym skanie.')
            break
        title=f"{opportunity['event']} · +{opportunity['profit_pct']:.2f}%"
        lines=[f"Kandydat surebeta · {opportunity['sport']}",title,opportunity['market']]
        lines += [f"{leg['bookmaker']}: {leg['selection']} @ {leg['odds']:g} — {leg['stake']:.2f} zł" for leg in opportunity['legs']]
        lines += [f"Wyliczony zysk: {opportunity['profit']:.2f} zł / {opportunity['budget']:.2f} zł",'Dwa odczyty porównywarki nie potwierdzają dostępności u bukmacherów. Zweryfikuj kursy, podatki i zasady.',url]
        success=False
        if channels['telegram']:
            try:
                response=send(f'https://api.telegram.org/bot{token}/sendMessage',{'chat_id':chat,'text':'\n'.join(lines),'disable_web_page_preview':True})
                if response.get('ok') is not True:raise RuntimeError('Usługa nie przyjęła alertu.')
                success=True
            except Exception:errors.append('Telegram nie przyjął alertu. Sprawdź konfigurację bota i chat ID.')
        if channels['push'] and time.monotonic()<deadline:
            try:
                response=send('https://api.onesignal.com/notifications',{'app_id':app_id,'included_segments':['Total Subscriptions'],'target_channel':'push','headings':{'en':'Kandydat surebeta – sprawdź kursy'},'contents':{'en':title+' · '+opportunity['market']},'url':url},{'Authorization':'Key '+key})
                if not response.get('id'):
                    errors.append('Push: brak aktywnych odbiorców lub usługa odrzuciła wiadomość. Włącz powiadomienia na telefonie i sprawdź OneSignal.')
                else:success=True
            except Exception:errors.append('Push nie przyjął alertu. Sprawdź klucze OneSignal.')
        if success:
            record.update(last_sent=now,profit=opportunity['profit_pct']);accepted+=1
    state['sent']={key:value for key,value in sent.items() if now-value.get('last_seen',0)<14*24*3600}
    return {'accepted':accepted,'channels':channels,'errors':errors}
