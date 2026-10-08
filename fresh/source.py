"""Anonymous JSON reads from the same public endpoints used by the comparison site."""
from __future__ import annotations
import json
import io
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

BASE='https://dobrybuk.pl/api/odds/'

class RateLimited(RuntimeError):
    def __init__(self,retry_after=900):
        self.retry_after=max(60,min(86400,retry_after))
        super().__init__('Źródło ograniczyło zapytania (HTTP 429). Skan zostanie ponowiony po przerwie.')

def open_source(opening,request,timeout):
    try:return opening(request,timeout=timeout)
    except urllib.error.HTTPError as exc:
        raw=exc.read(4096);exc.fp=io.BytesIO(raw)
        try:body=json.loads(raw)
        except (ValueError,TypeError):body={}
        if exc.code==429 or isinstance(body,dict) and body.get('upstream_status')==429:
            try:delay=int(exc.headers.get('Retry-After','900'))
            except (ValueError,TypeError,AttributeError):delay=900
            raise RateLimited(delay) from None
        raise

def error_text(exc):
    """Report HTTP status and known reader errors without URLs or credentials."""
    if isinstance(exc,urllib.error.HTTPError):
        message=f'HTTP {exc.code}'
        try:
            body=json.loads(exc.read(4096))
            known={'Nie udało się połączyć ze źródłem w limicie czasu.': 'źródło nie odpowiedziało w limicie czasu',
                   'Źródło odrzuciło odczyt.': 'źródło odrzuciło odczyt',
                   'Źródło nie zwróciło JSON.': 'źródło zwróciło niepoprawną odpowiedź',
                   'Brak dostępu.': 'niezgodny token czytnika'}
            if isinstance(body,dict):
                detail=known.get(body.get('error'))
                if detail:message+=' — '+detail
                upstream=body.get('upstream_status')
                if isinstance(upstream,int) and 100<=upstream<=599:message+=f' (źródło: HTTP {upstream})'
        except (ValueError,OSError,AttributeError,TypeError):pass
        return message
    if isinstance(exc,(TimeoutError,urllib.error.URLError)):
        return 'Brak odpowiedzi źródła lub błąd połączenia.'
    return type(exc).__name__

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
    with open_source(opener,request,timeout) as response:
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
            except RateLimited:
                # Stop queued requests; don't retry during the provider's cooldown.
                for pending in jobs:pending.cancel()
                raise
            except Exception as exc:errors.append(f'Zdarzenie {event_id}: {error_text(exc)}')
    except TimeoutError:
        errors.append('Limit czasu szczegółów: pozostałe wydarzenia wrócą w kolejnym skanie.')
    finally:
        for future in jobs:future.cancel()
        pool.shutdown(wait=True,cancel_futures=True)
    return results,errors
