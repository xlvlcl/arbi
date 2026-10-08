"""New scanner: one catalogue request, targeted detail reads, second-read confirmation."""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

from engine import SPORTS, candidate_events, future_event, market_groups, opportunities, number
from source import fetch_json, details, error_text, RateLimited
import urllib.error
from notify import send_alerts
from insights import radar, valuebets

ROOT=Path(__file__).resolve().parent

def read(path):
    try:
        value=json.loads(path.read_text('utf-8'));return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def write(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    temporary.replace(path)

def valid_config(config):
    if not isinstance(config,dict):raise ValueError('Źródło nie zwróciło konfiguracji kosztów.')
    for key in ['tax_rate','winning_tax_rate']:
        if key not in config or not isinstance(config[key],(int,float)) or isinstance(config[key],bool) or not 0<=config[key]<1:raise ValueError('Nieprawidłowa konfiguracja kosztów.')
    if number(config.get('winning_tax_threshold'))<=0:raise ValueError('Nieprawidłowy próg kosztów wygranej.')
    return config

def run(root=ROOT,fetch=fetch_json,read_details=details,notify=send_alerts,env=None):
    env=os.environ if env is None else env
    root=Path(root);now=time.time();started=time.monotonic()
    output=root/'web/data/latest.json'; state_path=root/'state.json'
    previous=read(output);state=read(state_path)
    run_url=f"https://github.com/{env.get('GITHUB_REPOSITORY','xlvlcl/arbi')}/actions/runs/{env.get('GITHUB_RUN_ID','')}"
    status={'version':'NEW-1','state':'error','attempt_at':now,'last_success_at':previous.get('status',{}).get('last_success_at'),'message':'','run_url':run_url,'errors':[]}
    try:
        resume_at=number(state.get('source_resume_at',0))
        if now<resume_at:
            status['source_resume_at']=resume_at
            raise RuntimeError('Przerwa po limicie źródła (HTTP 429). Kolejna próba za '+str(max(1,int((resume_at-now+59)//60)))+' min.')
        budget=max(3,number(env.get('BANKROLL_PLN',50)))
        minimum=max(0,number(env.get('MIN_PROFIT_PCT',.35)))
        overrides=json.loads(env.get('BOOKMAKER_TAX_OVERRIDES','{}'))
        if not isinstance(overrides,dict) or any(not isinstance(x,(int,float)) or isinstance(x,bool) or not 0<=x<1 for x in overrides.values()):raise ValueError('Nieprawidłowe nadpisanie podatku.')
        deadline=started+max(30,min(110,number(env.get('SCAN_BUDGET_SECONDS',85))))
        print('1/5 Pobieram konfigurację i katalog wydarzeń.',flush=True)
        config=valid_config(fetch('config/',10))
        catalogue=fetch('events/',15)
        if not isinstance(catalogue,list) or not catalogue:raise ValueError('Źródło nie zwróciło wydarzeń.')
        eligible=[e for e in catalogue if isinstance(e,dict) and future_event(e,now)]
        strong=candidate_events(eligible,now,slack=-minimum/(100+minimum))
        near=candidate_events(eligible,now)
        strong_ids={e['id'] for e in strong}
        extras=[e for e in near if e['id'] not in strong_ids]
        near_ids={e['id'] for e in near}
        extras += [e for e in eligible if e['id'] not in strong_ids and e['id'] not in near_ids]
        sequence=int(state.get('sequence',0))+1
        if extras:
            offset=(sequence-1)*12%len(extras);extras=extras[offset:]+extras[:offset]
        cap=max(10,min(100,int(number(env.get('DETAIL_LIMIT',40)))))
        selected=strong[:cap]+extras[:max(0,cap-len(strong))]
        print(f'2/5 Katalog: {len(catalogue)} zdarzeń, nadchodzące: {len(eligible)}, szczegóły: {len(selected)}.',flush=True)
        first,errors=read_details(selected,deadline,fetch=fetch,workers=5)
        missing_events=[e for e in selected if e['id'] not in first]
        if missing_events and time.monotonic()<deadline-10:
            print(f"Ponawiam {len(missing_events)} nieudanych odczytów.",flush=True)
            retry,retry_errors=read_details(missing_events,deadline,fetch=fetch,workers=3)
            first.update(retry)
            errors=[error for error in errors if not any(error.startswith(f"Zdarzenie {event_id}:") for event_id in retry)]
            errors+=retry_errors
        status['errors']+=errors
        candidates=[];value_candidates=[]
        for detail in first.values():
            if future_event(detail,time.time()):
                candidates+=opportunities(detail,budget,minimum,config,overrides)
                value_candidates+=valuebets(detail,budget,config,overrides)
        targets={op['event_id'] for op in candidates+value_candidates}
        print(f'3/5 Ponowny odczyt: {len(targets)} zdarzeń z możliwym surebetem lub valuebetem.',flush=True)
        confirmed=[];confirmed_values=[];latest_details=dict(first)
        confirmation_complete=not targets
        if targets and time.monotonic()<deadline-10:
            time.sleep(1)
            second,errors=read_details([{'id':i} for i in targets],deadline,fetch=fetch,workers=4)
            status['errors']+=errors
            confirmation_complete=all(event_id in second for event_id in targets)
            first_ids={op['id'] for op in candidates}
            value_ids={op['id'] for op in value_candidates}
            latest_details.update(second)
            for detail in second.values():
                if future_event(detail,time.time()):
                    confirmed += [op for op in opportunities(detail,budget,minimum,config,overrides) if op['id'] in first_ids]
                    confirmed_values += [op for op in valuebets(detail,budget,config,overrides) if op['id'] in value_ids]
        confirmed.sort(key=lambda x:x['profit_pct'],reverse=True)
        for opportunity in confirmed:opportunity['confirmed_at']=time.time()
        confirmed_values.sort(key=lambda x:x['edge_pct'],reverse=True)
        for value in confirmed_values:value['confirmed_at']=time.time()
        watch=[]
        for detail in latest_details.values():
            if future_event(detail,time.time()):watch+=radar(detail,budget,config,overrides)
        watch=sorted(watch,key=lambda x:x['gap_pct'])[:160]
        for row in watch:row['observed_at']=time.time()
        # Failed mandatory candidate reads are visible as partial coverage, never silent full success.
        missing=len([e for e in selected if e['id'] not in first])
        if selected and not first:raise RuntimeError('Nie udało się odczytać szczegółów żadnego wytypowanego wydarzenia.')
        print(f'4/5 Potwierdzone okazje: {len(confirmed)}. Powiadomienia.',flush=True)
        notices=notify(confirmed,state,env=env)
        status['errors']+=notices['errors']
        state['sequence']=sequence
        limited=len(strong)>cap
        status.update(state='partial' if missing or not confirmation_complete or limited else 'ok',last_success_at=time.time(),message=(f'Odczytano katalog; {missing} szczegółów wymaga ponownej próby.' if missing else 'Nie ukończono potwierdzania wszystkich kandydatów.' if not confirmation_complete else f'Limit szczegółów: sprawdzono {cap} z {len(strong)} kandydatów.' if limited else 'Skan zakończony.'))
        books={};items=[];market_count=0
        for detail in first.values():
            for row in detail.get('all_odds',[]):
                book=row.get('bookmaker') or {}
                if book.get('slug'):books[book['slug']]={'name':book.get('name'),'logo':book.get('logo'),'url':book.get('website_url')}
        for event in eligible:
            for offer in event.get('best_odds',[]):
                book=offer.get('bookmaker') or {}
                if book.get('slug'):books[book['slug']]={'name':book.get('name'),'logo':book.get('logo'),'url':book.get('website_url')}
            groups=market_groups([x.get('market_type') for x in event.get('best_odds',[])],event.get('sport',''))
            market_count+=len(groups)
            items.append({'id':event['id'],'name':event.get('name'),'sport':SPORTS.get(event.get('sport'),event.get('sport')),'sport_code':event.get('sport'),'starts_at':event.get('event_date'),'league':(event.get('league') or {}).get('name'),'url':'https://dobrybuk.pl/kursy/mecz/'+event.get('slug',''),'market_count':len(groups),'odds':[{'code':x.get('market_type'),'value':number(x.get('odds_value')),'bookmaker':(x.get('bookmaker') or {}).get('name'),'slug':(x.get('bookmaker') or {}).get('slug')} for x in event.get('best_odds',[])]})
        payload={'version':'NEW-1','status':status,'opportunities':confirmed,'events':items,'bookmakers':books,'config':config,'notifications':notices,'stats':{'source_events':len(catalogue),'upcoming_events':len(eligible),'market_groups':market_count,'detail_reads':len(first),'candidate_events':len(strong),'detail_limit':cap,'candidate_coverage_complete':confirmation_complete and len(strong)<=cap and all(e['id'] in first for e in strong[:cap]),'sports':sorted({e.get('sport') for e in eligible}),'bookmakers':len(books),'confirmed':len(confirmed)},'source_note':'Kursy z publicznej porównywarki. Potwierdzenie oznacza ponowny odczyt źródła; źródło nie podaje czasu aktualizacji każdego kursu. Dostępne rynki zależą od oferty źródła.'}
        payload['radar']=watch
        payload['valuebets']=confirmed_values
        payload['stats'].update(radar=len(watch),valuebets=len(confirmed_values))
        write(state_path,state)
    except Exception as exc:
        if isinstance(exc,RateLimited):
            state['source_resume_at']=time.time()+exc.retry_after
            status['source_resume_at']=state['source_resume_at']
            write(state_path,state)
        message=error_text(exc) if isinstance(exc,(urllib.error.HTTPError,urllib.error.URLError,TimeoutError)) else str(exc)
        print('BŁĄD:',type(exc).__name__,message,flush=True)
        status['message']=message
        payload={**previous,'version':'NEW-1','status':status,'opportunities':[],'radar':[],'valuebets':[]}
        payload.setdefault('events',[]);payload.setdefault('stats',{})
    status['duration_seconds']=round(time.monotonic()-started,2)
    print('5/5 Zapisuję wynik i status:',status['state'],flush=True)
    write(output,payload)
    if env.get('GITHUB_OUTPUT'):
        with open(env['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:f.write('scan_state='+status['state']+'\n')
    return payload

def record_failure(root=ROOT):
    path=Path(root)/'web/data/latest.json';previous=read(path)
    old=previous.get('status',{})
    previous.update(version='NEW-1',opportunities=[],radar=[],valuebets=[],status={'version':'NEW-1','state':'error','attempt_at':time.time(),'last_success_at':old.get('last_success_at'),'message':'Proces skanera przekroczył limit lub został przerwany. Sprawdź log uruchomienia.','errors':[]})
    previous.setdefault('events',[]);previous.setdefault('stats',{})
    write(path,previous)
if __name__=='__main__':
    if '--record-failure' in sys.argv:record_failure()
    else:run()
