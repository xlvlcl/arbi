from __future__ import annotations
import json, os
from pathlib import Path
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

load_dotenv()
ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
SETTINGS=DATA/'settings.json'

DEFAULT={
    'bankroll':50.0,
    'min_profit_pct':0.35,
    'scan_interval_seconds':60,
    'max_quote_age_seconds':180,
    'dedupe_minutes':30,
    'recheck_delay_seconds':2,
    'sports':['Piłka nożna','Tenis','Koszykówka','Hokej','Piłka ręczna','MMA','Boks','Dart','Żużel','Baseball','Futbol amerykański','Tenis stołowy'],
    'source_url':'https://dobrybuk.pl/kursy',
    'telegram_token':'',
    'telegram_chat_id':'',
    'bookmaker_payout_factors':{},
    'host':'0.0.0.0',
    'port':8080,
    'headless':True,
}

ENV_MAP={'telegram_token':'TELEGRAM_BOT_TOKEN','telegram_chat_id':'TELEGRAM_CHAT_ID'}

class Settings:
    def __init__(self):
        self.data=dict(DEFAULT)
        self.load_file()
        for key,env in ENV_MAP.items():
            if os.getenv(env): self.data[key]=os.getenv(env)
        self.data['bankroll']=float(os.getenv('BANKROLL_PLN',self.data['bankroll']))
        self.data['min_profit_pct']=float(os.getenv('MIN_PROFIT_PCT',self.data['min_profit_pct']))
        self.data['scan_interval_seconds']=max(45,int(os.getenv('SCAN_INTERVAL_SECONDS',self.data['scan_interval_seconds'])))
        self.data['max_quote_age_seconds']=max(60,int(os.getenv('MAX_QUOTE_AGE_SECONDS',self.data['max_quote_age_seconds'])))

    def load_file(self):
        if SETTINGS.exists():
            try:self.data.update(json.loads(SETTINGS.read_text('utf-8')))
            except Exception:pass
    def save(self, updates):
        for k,v in updates.items():
            if k in DEFAULT:self.data[k]=v
        SETTINGS.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding='utf-8')
    def __getattr__(self,name):
        if name in self.data:return self.data[name]
        raise AttributeError(name)
    def public(self):
        d=dict(self.data)
        for k in ('telegram_token',):
            v=str(d.get(k,'')); d[k+'_configured']=bool(v); d[k]=('***'+v[-4:]) if len(v)>4 else ('***' if v else '')
        d['telegram_chat_configured']=bool(d.get('telegram_chat_id'))
        return d
settings=Settings()
