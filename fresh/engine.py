"""Independent market model and stake calculator. Python standard library only."""
from __future__ import annotations
import hashlib
import itertools
import math
import re
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone

SPORTS = {'football':'Piłka nożna','tennis':'Tenis','basketball':'Koszykówka','volleyball':'Siatkówka','hockey':'Hokej','handball':'Piłka ręczna','mma':'MMA','boxing':'Boks','esport':'Esport','darts':'Dart','speedway':'Żużel','baseball':'Baseball','american_football':'Futbol amerykański','table_tennis':'Tenis stołowy'}
TWO_WAY = {'tennis','table_tennis','volleyball','basketball','baseball','esport','darts'}
# Extraordinary prices from one comparison source require manual confirmation, not push.
MAX_AUTO_PROFIT_PCT = 12.0

def number(value):
    try:
        n=float(value)
        return n if math.isfinite(n) else 0.0
    except (TypeError,ValueError):
        return 0.0

def future_event(event, now):
    try:
        dt=datetime.fromisoformat(event['event_date'].replace('Z','+00:00'))
        if dt.tzinfo is None: return False
        return dt.timestamp() > now and not event.get('is_live') and not event.get('result')
    except (KeyError,ValueError,TypeError): return False

def market_groups(keys, sport):
    keys=set(keys); out=[]
    def add(code,label,outcomes):
        if all(k in keys for k,_ in outcomes):out.append({'key':code,'name':label,'outcomes':outcomes})
    if 'X' in keys:
        add('result','Wynik meczu — 1X2',[('1','1'),('X','X'),('2','2')])
    elif sport in TWO_WAY:
        add('winner','Zwycięzca',[('1','1'),('2','2')])
    if 'X' in keys:
        add('1-x2','1 lub X2',[('1','1'),('dc_x2','X2')])
        add('2-1x','2 lub 1X',[('2','2'),('dc_1x','1X')])
        add('x-12','Remis lub brak remisu',[('X','X'),('dc_12','12')])
    for k in sorted(keys):
        m=re.fullmatch(r'over(\d+)',k)
        if m:
            digits=m.group(1); line=int(digits)/10
            if line % 1 != 0.5: continue
            add('total-'+digits,f'Powyżej / poniżej {line:g}',[(k,f'Powyżej {line:g}'),('under'+digits,f'Poniżej {line:g}')])
        m=re.fullmatch(r'hcp_([mp])(\d+)_1',k)
        if m:
            sign,digits=m.groups();line=int(digits)/10
            if line % 1 != 0.5:continue
            value=(-line if sign=='m' else line)
            add('handicap-'+sign+digits,f'Handicap {value:+g}',[(k,'1'),(k[:-1]+'2','2')])
        if k.endswith('_yes') and k[:-4]+'_no' in keys:
            stem=k[:-4]
            # A yes/no pair refers to the same boolean proposition; no cross-market mixing.
            label='Obie drużyny strzelą' if stem in {'bts','btts'} else stem.replace('_',' ')
            add('boolean-'+stem,label,[(k,'Tak'),(stem+'_no','Nie')])
    add('aces','Więcej asów serwisowych',[('aces_h2h_1','1'),('aces_h2h_x','X'),('aces_h2h_2','2')])
    return out

def flatten_detail(event, default_tax=.12, overrides=None):
    overrides=overrides or {}; quotes={}
    for row in event.get('all_odds',[]):
        book=row.get('bookmaker') or {}; slug=str(book.get('slug') or book.get('name') or '')
        custom=book.get('custom_tax_rate')
        tax=overrides.get(slug, default_tax if custom is None else custom)
        if not isinstance(tax,(int,float)) or isinstance(tax,bool) or not math.isfinite(tax):continue
        if not slug or not 0<=tax<1:continue
        for key,raw in (row.get('odds') or {}).items():
            odds=number(raw)
            if odds<=1 or odds>10000:continue
            quotes.setdefault(key,[]).append({'bookmaker':book.get('name',slug),'slug':slug,'logo':book.get('logo',''),'url':row.get('event_url') or book.get('website_url',''),'odds':odds,'tax_rate':tax,'effective_odds':odds*(1-tax)})
    return quotes

def cash(value):
    return Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_DOWN)

def payout(stake_cents, leg, config):
    net_stake=cash(Decimal(stake_cents)/100 * (1-Decimal(str(leg['tax_rate']))))
    gross=cash(net_stake * Decimal(str(leg['odds'])))
    threshold=Decimal(str(config.get('winning_tax_threshold',2280)))
    if gross>threshold:
        gross=cash(gross*(1-Decimal(str(config.get('winning_tax_rate',.1)))))
    return int(gross*100)

def allocate(legs,budget=50,config=None,min_stake=1):
    config=config or {}; cents=int(cash(budget)*100)
    if cents<=0 or not legs:return None
    inverse=[1/number(x.get('effective_odds')) if number(x.get('effective_odds'))>0 else math.inf for x in legs]
    total=sum(inverse)
    if not math.isfinite(total) or total<=0:return None
    ideals=[int(cents*x/total) for x in inverse]; floor_min=int(min_stake*100)
    best=None
    # Explore cents around the equal-payout allocation, including tax rounding.
    for shifts in itertools.product(range(-3,4),repeat=len(legs)-1):
        stakes=[ideals[i]+shift for i,shift in enumerate(shifts)]
        stakes.append(cents-sum(stakes))
        if min(stakes)<floor_min:continue
        payouts=[payout(stake,leg,config) for stake,leg in zip(stakes,legs)]
        floor=min(payouts)
        if best is None or floor>best[0]:best=(floor,stakes,payouts)
    if best is None:return None
    floor,stakes,payouts=best
    return {'budget':cents/100,'payout':floor/100,'profit':(floor-cents)/100,'profit_pct':(floor-cents)/cents*100,
            'legs':[{**leg,'stake':stake/100,'payout':paid/100} for leg,stake,paid in zip(legs,stakes,payouts)]}

def opportunities(event,budget=50,min_profit=.35,config=None,overrides=None):
    config=config or {}; quotes=flatten_detail(event,number(config.get('tax_rate',.12)),overrides)
    result=[]
    for group in market_groups(quotes,event.get('sport','')):
        legs=[]
        for key,label in group['outcomes']:
            offers=sorted(quotes[key],key=lambda x:x['effective_odds'],reverse=True)
            leg={**offers[0],'selection':label,'market_code':key,'alternatives':offers[1:5]};legs.append(leg)
        if len({x['slug'] for x in legs})<2:continue
        if sum(1/x['effective_odds'] for x in legs)>=1:continue
        allocation=allocate(legs,budget,config)
        if not allocation or allocation['profit_pct']<min_profit or allocation['profit_pct']>MAX_AUTO_PROFIT_PCT:continue
        identity=f"{event['id']}|{group['key']}"
        result.append({'id':hashlib.sha256(identity.encode()).hexdigest()[:20],'event_id':event['id'],'event':event.get('name',''),'sport':SPORTS.get(event.get('sport'),event.get('sport','')),'sport_code':event.get('sport',''),'starts_at':event.get('event_date'),'market':group['name'],'market_key':group['key'],'source_url':'https://dobrybuk.pl/kursy/mecz/'+event.get('slug',''),'config':config,**allocation})
    return result

def candidate_events(events,now,slack=.025):
    ranked=[]
    for event in events:
        if not future_event(event,now):continue
        odds={x.get('market_type'):number(x.get('odds_value')) for x in event.get('best_odds',[]) if number(x.get('odds_value'))>1}
        scores=[sum(1/odds[key] for key,_ in group['outcomes']) for group in market_groups(odds,event.get('sport',''))]
        if scores and min(scores)<1+slack:ranked.append((min(scores),event))
    return [e for _,e in sorted(ranked,key=lambda x:x[0])]
