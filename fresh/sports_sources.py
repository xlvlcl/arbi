"""Bounded, key-free collectors. A source response is never a promise of coverage.

Caches stay in Actions cache, not in the public site or git data feed.
Only selected coupon evidence is published by sports_ai.
"""
from __future__ import annotations
import concurrent.futures, hashlib, json, re, time, unicodedata
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

SPORTS = {
 'football':('Piłka nożna','Soccer'), 'basketball':('Koszykówka','Basketball'),
 'tennis':('Tenis','Tennis'), 'volleyball':('Siatkówka','Volleyball'),
 'hockey':('Hokej','Ice Hockey'), 'handball':('Piłka ręczna','Handball'),
 'baseball':('Baseball','Baseball'), 'american_football':('Futbol amerykański','American Football'),
 'rugby':('Rugby','Rugby'), 'table_tennis':('Tenis stołowy','Table Tennis'),
 'badminton':('Badminton','Badminton'), 'darts':('Dart','Darts'),
 'snooker':('Snooker','Snooker'), 'cricket':('Krykiet','Cricket'),
 'mma':('MMA','Fighting'), 'boxing':('Boks','Boxing'),
 'motorsport':('Sporty motorowe','Motorsport'), 'esports':('Esport','ESports'),
}
OPENFOOTBALL = {'en.1':'Europe/London','en.2':'Europe/London','es.1':'Europe/Madrid',
 'fr.1':'Europe/Paris','it.1':'Europe/Rome','nl.1':'Europe/Amsterdam','pt.1':'Europe/Lisbon'}
SS_SPORTS=('football','basketball','tennis','cricket')
ATTRIBUTIONS=[{'name':'OpenFootball','url':'https://github.com/openfootball/football.json','license':'CC0'},
 {'name':'SportScore','url':'https://sportscore.com/','license':'attribution'},
 {'name':'TheSportsDB','url':'https://www.thesportsdb.com/','license':'API terms'}]

def norm(name):
 s=''.join(c for c in unicodedata.normalize('NFKD',str(name).lower().replace('ł','l').replace('ß','ss')) if not unicodedata.combining(c))
 s=re.sub(r'\b(fc|cf|afc|sc|sv)\b','',s);s=re.sub('[^a-z0-9]','',s)
 return {'legiawarsaw':'legiawarszawa','lechpoznan':'lechpoznan','intermilan':'internazionale','inter':'internazionale','leeds':'leedsunited','manchesterutd':'manchesterunited','psg':'parissaintgermain'}.get(s,s)

def ident(provider,value):return -int(hashlib.sha256((provider+':'+str(value)).encode()).hexdigest()[:12],16)
def stamp(value):
 try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp() if re.search(r'(Z|[+-]\d\d:\d\d)$',str(value)) else 0
 except ValueError:return 0
def pair(a,b,maximum=300):
 if isinstance(a,bool) or isinstance(b,bool):return None
 if not re.fullmatch(r'\d+',str(a)) or not re.fullmatch(r'\d+',str(b)):return None
 values=[int(a),int(b)]
 return values if max(values)<=maximum else None

def row(provider,sport,key,start,home,away,score,finished,league,url,now,**extra):
 if not start or not home or not away or norm(home)==norm(away):return None
 if any(re.fullmatch(r'(?:R\d+P\d+|TBD|TBC|Winner.*|Loser.*)',str(n),re.I) for n in (home,away)):return None
 return {'id':ident(provider,key),'sport':sport,'provider':provider,'start':start,
  'home':{'id':provider+':'+sport+':'+norm(home),'name':home,'short':home},
  'away':{'id':provider+':'+sport+':'+norm(away),'name':away,'short':away},
  'score':score,'finished':finished,'league':league,'source_url':url,'fetched_at':now,
  'max_age':7200,'score_basis':'unknown',**extra}

def parse_openfootball(data,league,season,now):
 rows=[];zone=ZoneInfo(OPENFOOTBALL[league]);url=f'https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{league}.json'
 for m in data.get('matches',[]):
  try:
   # Date-only fixtures can provide historical evidence, never kickoff matching.
   start=datetime.fromisoformat(m['date']+'T'+m.get('time','12:00')).replace(tzinfo=zone).timestamp()
   score_data=m.get('score');score=score_data.get('ft') if isinstance(score_data,dict) else None;score=pair(*score,maximum=30) if isinstance(score,list) and len(score)==2 else None
   c=row('OpenFootball','football',league+':'+m['date']+':'+m['team1']+':'+m['team2'],start,m['team1'],m['team2'],score,score is not None,league,url,now,score_basis='regulation',kickoff_known=bool(m.get('time')),source_ref={'provider':'OpenFootball','league':league,'season':season})
   if c:rows.append(c)
  except (KeyError,ValueError,TypeError):continue
 return rows

def parse_sportscore(data,sport,now):
 rows=[]
 if not isinstance(data,dict):return rows
 for m in data.get('matches',[]) or []:
  path=m.get('url','');start=stamp(m.get('time'));score=pair(m.get('home_score'),m.get('away_score')) if m.get('status')=='finished' else None
  if not path.startswith('/'+sport+'/match/') or '?' in path:continue
  # This API's summary does not distinguish football ET or tennis retirements.
  # Collect the evidence, but only basketball has an unambiguous final-score market here.
  basis='full_game' if sport=='basketball' else 'unknown'
  c=row('SportScore',sport,path,start,m.get('home'),m.get('away'),score,m.get('status')=='finished',m.get('competition',''), 'https://sportscore.com'+path,now,score_basis=basis,source_ref={'provider':'SportScore','sport':sport,'date':str(m.get('time',''))[:10]})
  if c:rows.append(c)
 return rows

def parse_sportsdb(data,sport,now):
 rows=[]
 for m in (data.get('events') or data.get('results') or []) if isinstance(data,dict) else []:
  if m.get('strSport')!=SPORTS[sport][1] or not m.get('idEvent'):continue
  raw=m.get('strTimestamp') or ((m.get('dateEvent') or '')+'T'+(m.get('strTime') or ''))
  start=stamp(raw if re.search(r'(Z|[+-]\d\d:\d\d)$',raw) else raw+'Z')
  finished=m.get('strStatus') in ('FT','Match Finished','AOT') and m.get('strPostponed')!='yes'
  score=pair(m.get('intHomeScore'),m.get('intAwayScore')) if finished else None
  basis='unknown'
  if sport=='football' and m.get('strStatus') in ('FT','NS','Not Started',None,'') and not m.get('intHomeScoreExtra') and not m.get('intAwayScoreExtra'):basis='regulation'
  if sport in ('basketball','baseball'):basis='full_game'
  if sport in ('volleyball','table_tennis','badminton','tennis'):
   basis='match_sets'
   if score and (not 2<=max(score)<=4 or min(score)>=max(score)):score=None;finished=False
  # Incomplete/community score anomalies are not passed off as final handball scores.
  if sport=='handball' and score and sum(score)<10:score=None;finished=False
  c=row('TheSportsDB',sport,m['idEvent'],start,m.get('strHomeTeam'),m.get('strAwayTeam'),score,finished,m.get('strLeague',''),f'https://www.thesportsdb.com/event/{m["idEvent"]}',now,score_basis=basis,source_ref={'provider':'TheSportsDB','sport':sport,'id':str(m['idEvent'])},team_refs=[m.get('idHomeTeam'),m.get('idAwayTeam')])
  if c:rows.append(c)
 return rows

def collect(cache,events,coupons,now,fetch):
 """One bounded cycle; returned rows retain their actual read timestamps."""
 cache=dict(cache);entries=cache.setdefault('entries',{});reports=cache.setdefault('reports',{});jobs={};today=datetime.fromtimestamp(now,timezone.utc).date();year=today.year-(today.month<7)
 def add(key,url,parser,args,ttl=3600):
  entry=entries.get(key,{})
  if 0<=now-entry.get('at',0)<ttl:return
  jobs[key]=(url,parser,args)
 for league in OPENFOOTBALL:
  for y in (year-1,year):
   season=f'{y}-{str(y+1)[-2:]}';add('of:'+league+':'+season,f'https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{league}.json',parse_openfootball,(league,season),3600 if y==year else 86400)
 # Current day plus a rotating past/future day; cache builds a modest shared history.
 cycle=int(cache.get('cycle',0));offsets=(0,1,-1-(cycle%14))
 for sport in SS_SPORTS:
  for offset in offsets:
   day=str(today+timedelta(days=offset));add('ss:'+sport+':'+day,'https://sportscore.com/api/v1/fixtures/?'+urlencode({'sport':sport,'date':day,'limit':200}),parse_sportscore,(sport,),900 if offset>=0 else 86400)
 # 18 calls at most per run, plus at most 8 result lookups: below free 30/min limit.
 for sport,(_,source_name) in SPORTS.items():
  day=str(today+timedelta(days=cycle%2));add('ts:'+sport+':'+day,'https://www.thesportsdb.com/api/v1/json/123/eventsday.php?'+urlencode({'d':day,'s':source_name}),parse_sportsdb,(sport,),900)
 result_refs=[]
 for coupon in coupons:
  for leg in coupon.get('legs',[]):
   ref=leg.get('source_ref',{})
   if ref.get('provider')=='SportScore' and ref.get('sport') in SS_SPORTS and re.fullmatch(r'\d{4}-\d{2}-\d{2}',ref.get('date','')):
    sport,day=ref['sport'],ref['date'];add('ss:'+sport+':'+day,'https://sportscore.com/api/v1/fixtures/?'+urlencode({'sport':sport,'date':day,'limit':200}),parse_sportscore,(sport,),900)
    if len(jobs)>60:break
 for c in coupons:
  for leg in c.get('legs',[]):
   ref=leg.get('source_ref',{})
   if ref.get('provider')=='TheSportsDB' and ref.get('sport') in SPORTS and re.fullmatch(r'\d+',ref.get('id','')) and ref not in result_refs:result_refs.append(ref)
 for ref in result_refs[-8:]:add('lookup:'+ref['id'],'https://www.thesportsdb.com/api/v1/json/123/lookupevent.php?id='+ref['id'],parse_sportsdb,(ref['sport'],),900)
 def get(item):
  key,(url,parser,args)=item;raw=fetch(url);rows=parser(raw,*args,now)
  return key,{'at':now,'rows':rows},len(raw.get('matches',raw.get('events') or []) or [])
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  future_map={pool.submit(get,item):item[0] for item in jobs.items()}
  for future in concurrent.futures.as_completed(future_map):
   key=future_map[future]
   try:
    key,entry,count=future.result();entries[key]=entry;reports[key]={'at':now,'state':'ok','received':count,'usable':len(entry['rows'])}
   except Exception as exc:reports[key]={'at':now,'state':'error','error':type(exc).__name__}
 # No invented freshness: old rows remain history only; limit storage to 45 days of cache entries.
 entries={k:v for k,v in entries.items() if now-v.get('at',0)<45*86400};cache['entries']=entries;cache['cycle']=cycle+1
 merged={}
 for entry in sorted(entries.values(),key=lambda x:x['at']):
  for m in entry['rows']:merged[m['id']]=m
 rows=list(merged.values());coverage=[]
 for sport,(label,_) in SPORTS.items():
  subset=[m for m in rows if m['sport']==sport];recent=[m for m in subset if 0<=now-m['fetched_at']<=7200]
  sport_reports=[v for k,v in reports.items() if k.startswith(('ss:'+sport+':','ts:'+sport+':')) or sport=='football' and k.startswith('of:')]
  coverage.append({'sport':sport,'label':label,'records':len(subset),'fresh_records':len(recent),'history':sum(m['score'] is not None for m in subset),'sources':sorted({m['provider'] for m in subset}),'last_checked':max((r['at'] for r in sport_reports),default=0),'source_errors':sum(r['state']=='error' for r in sport_reports),'eligible':0,'state':'partial' if subset else 'no_data'})
 return rows,cache,coverage
