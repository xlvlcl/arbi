"""Publish a compact scan snapshot without exposing source or notification credentials."""
import copy
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from source import NoRedirect
from scan import read, write

ROOT=Path(__file__).resolve().parent

def compact(data):
    result=copy.deepcopy(data)
    for event in result.get('events',[]):
        event['odds']=[x for x in event.get('odds',[]) if x.get('code') in ('1','X','2')]
    return result

def publish(root=ROOT,env=None,open_request=None,now=None):
    env=os.environ if env is None else env;now=time.time() if now is None else now
    reader=env.get('SOURCE_READER_URL','').strip();token=env.get('SOURCE_READER_TOKEN','').strip()
    if not reader:return 'disabled'
    parts=urlsplit(reader)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('','/') or len(token)<32 or '\n' in token or '\r' in token:
        raise ValueError('Nieprawidłowa konfiguracja publikacji wyniku.')
    state_path=Path(root)/'state.json';state=read(state_path)
    # At least 90 s between writes => at most 960 per day, within KV Free's 1,000.
    elapsed=now-float(state.get('feed_published_at',0))
    if 0<=elapsed<90:return 'throttled'
    data=read(Path(root)/'web/data/latest.json')
    if data.get('version')!='NEW-1' or not data.get('status',{}).get('attempt_at'):
        raise ValueError('Brak poprawnego wyniku skanera do publikacji.')
    raw=json.dumps(compact(data),ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if len(raw)>8*1024*1024:raise ValueError('Wynik skanera przekracza limit publikacji.')
    request=urllib.request.Request(reader.rstrip('/')+'/feed/latest',data=raw,method='PUT',headers={
        'Content-Type':'application/json','Content-Length':str(len(raw)),
        'User-Agent':'Mozilla/5.0','Accept':'application/json',
        'Authorization':'Bearer '+token,'X-Arbi-Attempt':str(data['status']['attempt_at'])})
    opening=open_request or urllib.request.build_opener(NoRedirect()).open
    with opening(request,timeout=20) as response:
        result=json.loads(response.read(4096))
        if result.get('ok') is not True:raise RuntimeError('Czytnik nie potwierdził zapisu wyniku.')
    state['feed_published_at']=now;write(state_path,state)
    return 'published'

if __name__=='__main__':
    try:print('Publikacja wyniku Cloudflare:',publish(),flush=True)
    except urllib.error.HTTPError as exc:
        print(f'::warning::Wynik Cloudflare: HTTP {exc.code}. Dla HTTP 503 sprawdź binding KV DATA; dla 401 zgodność tokenów. Skan i alerty działają niezależnie.',flush=True)
    except Exception as exc:
        print('::warning::Nie udało się opublikować wyniku Cloudflare ('+type(exc).__name__+'). Pozostaje odczyt wyniku z GitHub.',flush=True)
