"""Radar and market-consensus estimates built from complete source markets."""
import hashlib
from statistics import median
from engine import SPORTS, allocate, cash, flatten_detail, market_groups, payout


def identity(event, group, suffix=''):
    return hashlib.sha256(f"{event['id']}|{group['key']}|{suffix}".encode()).hexdigest()[:20]


def metadata(event, group):
    return {'event_id':event['id'],'event':event.get('name',''),'sport_code':event.get('sport'),
            'sport':SPORTS.get(event.get('sport'),event.get('sport')),'starts_at':event.get('event_date'),
            'market':group['name'],'market_key':group['key'],
            'source_url':'https://dobrybuk.pl/kursy/mecz/'+event.get('slug','')}


def radar(event, budget, config, overrides=None, max_gap=35):
    quotes=flatten_detail(event,config['tax_rate'],overrides);result=[]
    for group in market_groups(quotes,event.get('sport','')):
        legs=[];available=set()
        for key,label in group['outcomes']:
            offers=quotes[key];available.update(q['slug'] for q in offers)
            best=max(offers,key=lambda q:q['effective_odds'])
            legs.append({**best,'selection':label,'market_code':key})
        inverse=sum(1/leg['effective_odds'] for leg in legs)
        gap=(inverse-1)*100
        if gap<0 or gap>max_gap:continue
        calculation=allocate(legs,budget,config)
        if not calculation:continue
        result.append({**metadata(event,group),'id':identity(event,group),'config':config,
                       'gap_pct':gap,'bookmakers':len(available),
                       'tier':'market' if len(available)<2 else 'near' if gap<=1.5 else 'watch',
                       **calculation})
    return sorted(result,key=lambda x:x['gap_pct'])


def valuebets(event,budget,config,overrides=None,min_edge=5,min_refs=5):
    quotes=flatten_detail(event,config['tax_rate'],overrides);result=[]
    cents=int(cash(budget)*100)
    if cents<=0:return []
    for group in market_groups(quotes,event.get('sport','')):
        keys=[key for key,_ in group['outcomes']]
        by_key={key:{q['slug']:q for q in quotes[key]} for key in keys}
        complete=set.intersection(*(set(by_key[key]) for key in keys))
        if len(complete)<min_refs+1:continue
        for key,label in group['outcomes']:
            choices=[]
            for target_book in sorted(complete):
                target=by_key[key][target_book]
                if not 1.35<=target['odds']<=8:continue
                refs=complete-{target_book}
                probabilities=[(1/by_key[key][book]['odds'])/sum(1/by_key[k][book]['odds'] for k in keys) for book in sorted(refs)]
                probability=median(probabilities)
                dispersion=median(abs(p-probability) for p in probabilities)/probability
                if dispersion>.08:continue
                next_price=max(by_key[key][book]['odds'] for book in refs)
                if target['odds']/next_price-1>.30:continue
                paid=payout(cents,target,config)/100
                expected=paid*probability-cents/100
                edge=expected/(cents/100)*100
                if edge+1e-9<min_edge:continue
                choices.append({**metadata(event,group),'id':identity(event,group,key+'|'+target_book),
                                'leg':{**target,'selection':label,'market_code':key},'config':config,
                                'probability':probability,'reference_books':len(refs),'dispersion_pct':dispersion*100,
                                'budget':cents/100,'payout':paid,'edge_pct':edge,'expected_profit':expected,
                                'fair_odds':1/probability,'estimated_loss_pct':(1-probability)*100})
            if choices:result.append(max(choices,key=lambda x:x['edge_pct']))
    return sorted(result,key=lambda x:x['edge_pct'],reverse=True)
