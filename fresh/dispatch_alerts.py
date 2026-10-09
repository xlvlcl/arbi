"""Send notifications only after a scan snapshot is committed and available to the site."""
from pathlib import Path
import os
import time
from datetime import datetime
from engine import MAX_AUTO_PROFIT_PCT, number
from scan import read, write
from notify import send_alerts

ROOT=Path(__file__).resolve().parent

def dispatch(root=ROOT, env=None, now=None, notify=send_alerts):
    env=os.environ if env is None else env
    now=time.time() if now is None else now
    root=Path(root)
    current=read(root/'web/data/latest.json')
    status=current.get('status') or {}
    if status.get('state') not in ('ok','partial') or now-number(status.get('last_success_at'))>300:
        print('Alerty pominięte: brak aktualnego zakończonego skanu.', flush=True)
        return {'accepted':0, 'skipped':'stale'}
    rows=[]
    for op in current.get('opportunities',[]):
        try:
            starts=datetime.fromisoformat(op['starts_at'].replace('Z','+00:00')).timestamp()
        except (KeyError,TypeError,ValueError,AttributeError):
            continue
        if (starts>now and 0<=now-number(op.get('confirmed_at'))<=300
            and 0<number(op.get('profit_pct'))<=MAX_AUTO_PROFIT_PCT):
            rows.append(op)
    state_path=root/'state.json'
    state=read(state_path)
    result=notify(rows,state,env=env,now=now)
    write(state_path,state)
    print(f"Alerty po publikacji: {result.get('accepted',0)} zaakceptowanych, {len(result.get('errors',[]))} błędów.",flush=True)
    return result

if __name__=='__main__':
    dispatch()
