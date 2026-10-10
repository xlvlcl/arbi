import copy,json,sys,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import sports_ai as s
NOW=2000000000

def iso(t):return datetime.fromtimestamp(t,timezone.utc).isoformat()
def match(mid=1,start=NOW+3600,score=None):return {'id':mid,'start':start,'home':{'id':10,'name':'Alpha FC','short':'Alpha'},'away':{'id':20,'name':'Beta SV','short':'Beta'},'score':score,'finished':score is not None,'league':'bl1','source_url':f'https://api.openligadb.de/getmatchdata/{mid}','fetched_at':NOW}
def context():
    m=match();history=[match(i,NOW-i*86400,[i%3,1]) for i in range(2,15)]
    return s.evidence(m,history,NOW)
def pick(mid=1):return {'match_id':mid,'market':'over25','probability':.7,'analysis':'W historii są wyniki do analizy liczby goli. To ocena o ograniczonej wiarygodności.','risks':'Brak składów i danych o kontuzjach.','evidence_ids':[2,3],'context':context(),'model':'gemini-3.5-flash-lite'}
def event(mid=1,home='Alpha',away='Beta',odds=2):return {'id':mid,'name':home+' - '+away,'sport_code':'football','starts_at':iso(NOW+3600),'odds':[{'code':'over25','value':odds,'slug':'book','bookmaker':'Book'}]}
def raw(mid=1,finished=True,kind='After90Minutes',a=2,b=1):return {'matchID':mid,'matchDateTimeUTC':iso(NOW-10000),'matchIsFinished':finished,'leagueShortcut':'bl1','team1':{'teamId':10,'teamName':'Alpha'},'team2':{'teamId':20,'teamName':'Beta'},'matchResults':[{'resultTypeID':1,'pointsTeam1':0,'pointsTeam2':0},{'resultTypeID':2,'resultTypeKind':kind,'pointsTeam1':a,'pointsTeam2':b}]}

class SportsTests(unittest.TestCase):
 def test_finished_regular_time_only(self):
    self.assertEqual(s.compact_match(raw())['score'],[2,1])
    self.assertIsNone(s.compact_match(raw(finished=False))['score'])
    self.assertIsNone(s.compact_match(raw(kind='AfterExtraTime'))['score'])
    self.assertIsNone(s.compact_match(raw(a=-1))['score'])
 def test_match_exact_teams_time_and_no_ambiguity(self):
    self.assertEqual(s.match_event(event(),[match()])['id'],1)
    self.assertIsNone(s.match_event(event(home='Beta',away='Alpha'),[match()]))
    self.assertIsNone(s.match_event(event(),[match(),match(2)]))
    self.assertIsNone(s.match_event(event(),[match(start=NOW+86400)]))
 def test_history_has_no_future_data_or_odds(self):
    c=context();self.assertEqual(len(c['home_history']),12)
    self.assertNotIn('odds',json.dumps(c));self.assertNotIn('bookmaker',json.dumps(c))
    self.assertTrue(all(s.timestamp(r['date'])<NOW for r in c['home_history']))
    self.assertIsNone(s.evidence(match(),[match(2,NOW-10000,[1,1])],NOW))
 def test_ai_request_contains_only_sports_context_and_validates_evidence(self):
    calls=[]
    def fetch(url,body,key):
        calls.append((url,body,key));p=pick();p.pop('context');p.pop('model')
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({'picks':[p]})}]}}]}
    result=s.analyze_ai([context()],'private-key','gemini-3.5-flash-lite',fetch)
    self.assertEqual(len(result),1);body=json.dumps(calls[0][1]);self.assertNotIn('private-key',body);self.assertNotIn('"odds"',body);self.assertNotIn('"bookmaker"',body)
    def invalid(url,body,key):
        p=pick();p['evidence_ids']=[99999,88888]
        return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({'picks':[p]})}]}}]}
    self.assertEqual(s.analyze_ai([context()],'key','gemini-test',invalid),[])
 def test_results_for_supported_markets(self):
    m=match(score=[2,1])
    for market,value in {'1':True,'X':False,'2':False,'over25':True,'under25':False,'bts_yes':True,'bts_no':False}.items():self.assertEqual(s.result_for(market,m),value)
    self.assertIsNone(s.result_for('corners_over85',m));self.assertIsNone(s.result_for('1',match()))
 def test_automatic_settlement_pending_lost_and_correction(self):
    coupon={'id':'a','state':'open','legs':[{'match_id':1,'market_code':'1','result':None},{'match_id':2,'market_code':'over25','result':None}]}
    s.settle([coupon],[match(start=NOW-10000,score=[2,0])],NOW);self.assertEqual(coupon['state'],'open')
    m2=match(2,NOW-10000,[0,1]);s.settle([coupon],[m2],NOW);self.assertEqual(coupon['state'],'lost')
    m2['score']=[2,1];s.settle([coupon],[m2],NOW);self.assertEqual(coupon['state'],'won');self.assertEqual(len(coupon['result_history']),2)
    m2['finished']=False;m2['score']=None;s.settle([coupon],[m2],NOW);self.assertEqual(coupon['state'],'open')
 def test_stale_result_cannot_settle(self):
    c={'state':'open','legs':[{'match_id':1,'market_code':'1','result':None}]};m=match(start=NOW-10000,score=[1,0]);m['fetched_at']=NOW-1801;s.settle([c],[m],NOW);self.assertEqual(c['state'],'open')
 def test_ako_same_book_no_repeat_probabilities_independent_of_odds(self):
    m1,m2=match(),match(2);m2['home']={'id':30,'name':'Gamma','short':'Gamma'};m2['away']={'id':40,'name':'Delta','short':'Delta'}
    p1,p2=pick(),pick(2);events=[event(),event(2,'Gamma','Delta')]
    coupons=s.make_coupons([p1,p2],events,[m1,m2],NOW,[]);self.assertEqual(len(coupons),1);self.assertEqual(coupons[0]['odds'],4);self.assertAlmostEqual(coupons[0]['probability'],.49)
    events[0]['odds'][0]['value']=2.5;other=s.make_coupons([p1,p2],events,[m1,m2],NOW,[]);self.assertAlmostEqual(other[0]['probability'],.49)
    self.assertEqual(s.make_coupons([p1,p2],events,[m1,m2],NOW,coupons),[])
 def test_missing_key_no_ai_call_but_results_run(self):
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);s.write(root/'web/data/latest.json',{'status':{'state':'error'},'events':[]});calls=[]
        def fetch(url,*args):calls.append(url);return [raw()]
        output=s.run(root,{},fetch,NOW);self.assertEqual(output['status']['ai'],'not_configured');self.assertTrue(calls);self.assertTrue(all(url.startswith('https://api.openligadb.de/') for url in calls));self.assertEqual(output['coupons'],[])
 def test_source_failure_preserves_archive_and_reports_error(self):
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);c={'id':'saved','state':'open','legs':[{'match_id':1,'market_code':'1','result':None}]};s.write(root/'web/data/ai-coupons.json',{'coupons':[c]})
        def fail(*args):raise TimeoutError()
        output=s.run(root,{},fail,NOW);self.assertEqual(output['coupons'][0]['state'],'open');self.assertEqual(output['status']['results'],'error')

if __name__=='__main__':unittest.main()
