"""Anonymous JSON reads from the same public endpoints used by the comparison site."""
from __future__ import annotations
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

BASE='https://dobrybuk.pl/api/odds/'

def fetch_json(path,timeout=10,base=BASE):
    url=base+path
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
    with urllib.request.urlopen(request,timeout=timeout) as response:
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
