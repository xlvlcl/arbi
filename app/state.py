from __future__ import annotations
import json,time,asyncio
from pathlib import Path

class State:
    def __init__(self,path:Path):
        self.path=path; self.lock=asyncio.Lock(); self.latest=[]; self.errors=[]; self.last_scan=0; self.stats={}; self.sent={}
        self.load()
    def load(self):
        try:self.sent=json.loads(self.path.read_text('utf-8')).get('sent',{})
        except Exception: self.sent={}
    async def save(self):
        async with self.lock:self.path.write_text(json.dumps({'sent':self.sent},ensure_ascii=False,indent=2),encoding='utf-8')
    async def should_alert(self,key,profit,minutes):
        now=time.time(); old=self.sent.get(key)
        if not old or now-float(old.get('at',0))>minutes*60:
            self.sent[key]={'at':now,'profit':profit}; await self.save(); return True
        if profit>=float(old.get('profit',0))+0.75:
            self.sent[key]={'at':now,'profit':profit}; await self.save(); return True
        return False
    def snapshot(self):
        cutoff=time.time()-48*3600
        self.sent={k:v for k,v in self.sent.items() if float(v.get('at',0))>cutoff}
        return {'latest':[a.to_dict() for a in self.latest],'last_scan':self.last_scan,'errors':self.errors[-10:],'stats':self.stats}
