import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sports_ai as ai
import sports_sources as s
NOW=1791720000

class SourceTests(unittest.TestCase):
 def test_openfootball_time_and_score_semantics(self):
  data={'matches':[{'date':'2026-10-10','time':'15:00','team1':'Arsenal FC','team2':'Leeds United FC','score':{'ft':[2,1],'et':[3,1]}},{'date':'2026-10-12','team1':'Arsenal FC','team2':'Leeds United FC','score':[None,None]}]}
  rows=s.parse_openfootball(data,'en.1','2026-27',NOW)
  self.assertEqual(len(rows),2);self.assertEqual(rows[0]['score'],[2,1]);self.assertEqual(rows[0]['start'],s.stamp('2026-10-10T14:00:00Z'));self.assertFalse(rows[1]['kickoff_known']);self.assertIsNone(rows[1]['score'])
 def test_namespaced_ids_and_no_placeholders(self):
  self.assertNotEqual(s.ident('A',1),s.ident('B',1));self.assertLess(s.ident('A',1),0)
  self.assertIsNone(s.row('A','tennis',1,NOW,'R64P61','R64P62',None,False,'x','https://example.com',NOW))
 def test_sportscore_no_guess_of_regulation_or_retirement(self):
  def raw(sport):return {'matches':[{'url':f'/{sport}/match/a-vs-b/abc/','home':'Alpha','away':'Beta','time':'2026-10-10T12:00:00Z','home_score':'3','away_score':'2','status':'finished'}]}
  for sport in ('football','tennis'):
   m=s.parse_sportscore(raw(sport),sport,NOW)[0];self.assertEqual(ai.allowed_markets(m),{});self.assertIsNone(ai.result_for('1',m))
  m=s.parse_sportscore(raw('basketball'),'basketball',NOW)[0];self.assertTrue(ai.result_for('1',m));self.assertNotIn('X',ai.allowed_markets(m));self.assertIsNone(ai.result_for('over25',m))
 def test_sportsdb_unknown_final_score_and_bad_handball(self):
  raw={'idEvent':'123','strSport':'Handball','strHomeTeam':'Alpha','strAwayTeam':'Beta','strTimestamp':'2026-10-10T12:00:00','strStatus':'FT','intHomeScore':'3','intAwayScore':'2'}
  m=s.parse_sportsdb({'events':[raw]},'handball',NOW)[0];self.assertIsNone(m['score']);self.assertFalse(m['finished'])
  raw.update(strSport='Soccer',strStatus='AOT',intHomeScore='2',intAwayScore='1')
  m=s.parse_sportsdb({'events':[raw]},'football',NOW)[0];self.assertIsNone(ai.result_for('1',m))
 def test_cross_sport_names_never_match(self):
  m=s.row('TheSportsDB','basketball',1,NOW+3600,'Alpha','Beta',None,False,'x','https://example.com',NOW,score_basis='full_game')
  e={'sport_code':'football','name':'Alpha - Beta','starts_at':'2026-10-11T13:00:00+00:00'}
  self.assertIsNone(ai.match_event(e,[m]))
 def test_history_does_not_mix_sports_or_providers(self):
  target=s.row('TheSportsDB','basketball',1,NOW+3600,'Alpha','Beta',None,False,'x','https://example.com',NOW,score_basis='full_game')
  history=[]
  for i in range(7):
   m=copy.deepcopy(target);m.update(id=i+1,start=NOW-(i+1)*86400,score=[90,85],finished=True);history.append(m)
  self.assertIsNotNone(ai.evidence(target,history,NOW));history[0]['sport']='football';history[1]['provider']='Other'
  self.assertIsNone(ai.evidence(target,history,NOW))
 def test_cache_failure_does_not_refresh_old_rows(self):
  m=s.row('SportScore','basketball',1,NOW-10000,'Alpha','Beta',[90,85],True,'x','https://example.com',NOW-10000,score_basis='full_game')
  cache={'entries':{'old':{'at':NOW-10000,'rows':[m]}}}
  def fail(url):raise TimeoutError()
  rows,updated,coverage=s.collect(cache,[],[],NOW,fail)
  self.assertEqual(rows[0]['fetched_at'],NOW-10000);self.assertFalse(ai.fresh_match(rows[0],NOW));self.assertEqual(len(coverage),18)
 def test_read_only_bounded_collection(self):
  calls=[]
  def fetch(url):calls.append(url);return {'matches':[],'events':[]}
  _,cache,cov=s.collect({},[],[],NOW,fetch)
  self.assertLessEqual(len(calls),50);self.assertEqual(sum('thesportsdb.com' in u for u in calls),18)
  self.assertTrue(all(u.startswith('https://') for u in calls));self.assertTrue(all(c['state']=='no_data' for c in cov))
  calls.clear();s.collect(cache,[],[],NOW+1,fetch);self.assertLessEqual(len(calls),24)

if __name__=='__main__':unittest.main()
