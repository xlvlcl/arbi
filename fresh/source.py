"""Anonymous JSON reads from the same public endpoints used by the comparison site."""
from __future__ import annotations
import json
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

BASE='https://dobrybuk.pl/api/odds/'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise urllib.error.HTTPError(req.full_url,code,'Czytnik nie może przekierować tokenu.',headers,fp)

def fetch_json(path,timeout=10,base=BASE):
    if not re.fullmatch(r'(?:config|events|bookmakers|sport-tabs)/|events/[0-9]+/',path):
        raise ValueError('Nieprawidłowa ścieżka źródła.')
    headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'}
    opener=urllib.request.urlopen
    reader=os.environ.get('SOURCE_READER_URL','').strip()
    if reader and base==BASE:
        parts=urlsplit(reader)
        if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('','/'):
            raise ValueError('SOURCE_READER_URL musi być adresem HTTPS czytnika bez ścieżki i parametrów.')
        token=os.environ.get('SOURCE_READER_TOKEN','').strip()
        if len(token)<32 or '\n' in token or '\r' in token:
            raise ValueError('Brak poprawnego SOURCE_READER_TOKEN (minimum 32 znaki).')
        base=reader.rstrip('/')+'/api/odds/'
        headers['Authorization']='Bearer '+token
        opener=urllib.request.build_opener(NoRedirect()).open
    url=base+path
    request=urllib.request.Request(url,headers=headers)
    with opener(request,timeout=timeout) as response:
        if response.status!=200:raise RuntimeError(f'HTTP {response.status}')
        raw=response.read(24*1024*1024+1)
        if len(raw)>24*1024*1024:raise ValueError('Odpowiedź źródła przekroczyła limit rozmiaru.')
        return json.loads(raw)

def details(events,deadline,fetch=fetch_json,workers=5):
    results={}; errors=[]
    pool=ThreadPoolExecutor(max_workers=workers)
    jobs={pool.submit(fetch,f"events/{e['id']}/",8):e['id'] for e in events if time.monotonic()<deadline}
    try:
        for future in as_completed(jobs,timeout=max(.1,deadline-time.monotonic())):
            event_id=jobs[future]
            try:
                data=future.result()
                if not isinstance(data,dict) or data.get('id')!=event_id or not isinstance(data.get('all_odds'),list):
                    raise ValueError('Nieprawidłowy format szczegółów wydarzenia.')
                results[event_id]=data
            except Exception as exc:errors.append(f'Zdarzenie {event_id}: {type(exc).__name__}')
    except TimeoutError:
        errors.append('Limit czasu szczegółów: pozostałe wydarzenia wrócą w kolejnym skanie.')
    finally:
        for future in jobs:future.cancel()
        pool.shutdown(wait=True,cancel_futures=True)
    return results,errors
