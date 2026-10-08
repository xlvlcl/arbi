import copy
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import allocate, candidate_events, flatten_detail, future_event, market_groups, opportunities, payout
from scan import run, read, write, valid_config
from build import build
from notify import due, send_alerts
from source import details

CONFIG={'tax_rate':.12,'winning_tax_threshold':2280,'winning_tax_rate':.1}

def event(tax=0):
    return {'id':1,'name':'A - B','slug':'a-b-1','sport':'tennis','event_date':'2099-01-01T20:00:00+02:00','league':{'name':'Test'},'best_odds':[{'market_type':'1','odds_value':2.2,'bookmaker':{'slug':'a','name':'A'}},{'market_type':'2','odds_value':2.2,'bookmaker':{'slug':'b','name':'B'}}],'all_odds':[{'bookmaker':{'slug':'a','name':'A','custom_tax_rate':tax},'odds':{'1':'2.20','2':'1.80'},'event_url':'https://a.example/'},{'bookmaker':{'slug':'b','name':'B','custom_tax_rate':tax},'odds':{'1':'1.80','2':'2.20'},'event_url':'https://b.example/'}]}

def fake_fetch(path,timeout):
    if path=='config/':return copy.deepcopy(CONFIG)
    if path=='events/':return [event()]
    raise AssertionError(path)

def fake_notify(ops,state,**kwargs):return {'accepted':0,'channels':{'telegram':False,'push':False},'errors':[]}

class Markets(unittest.TestCase):
    def test_football_requires_draw(self):self.assertFalse(market_groups(['1','2'],'football'))
    def test_two_way_known_sport(self):self.assertEqual(len(market_groups(['1','2'],'tennis')),1)
    def test_double_chance_is_not_a_partition(self):self.assertFalse(market_groups(['dc_1x','dc_x2','dc_12'],'football'))
    def test_complementary_double_chance(self):self.assertTrue(any(g['key']=='1-x2' for g in market_groups(['1','X','2','dc_x2'],'football')))
    def test_dnb_does_not_claim_profit_on_draw(self):self.assertFalse(market_groups(['dnb_1','dnb_2'],'football'))
    def test_handicap_half_line(self):self.assertEqual(len(market_groups(['hcp_m15_1','hcp_m15_2'],'football')),1)
    def test_handicap_whole_line_is_skipped(self):self.assertFalse(market_groups(['hcp_m10_1','hcp_m10_2'],'football'))
    def test_yes_and_no_same_proposition(self):self.assertEqual(len(market_groups(['bts_yes','bts_no'],'football')),1)
    def test_no_cross_line_pairing(self):self.assertFalse(market_groups(['over15','under25'],'football'))
    def test_invalid_tax_does_not_become_free(self):self.assertFalse(flatten_detail(event(tax='bad')))
    def test_tax_removes_raw_arbitrage(self):self.assertFalse(opportunities(event(.12),config=CONFIG))
    def test_no_arbitrage_with_one_book(self):
        e=event();e['all_odds']=e['all_odds'][:1];self.assertFalse(opportunities(e,config=CONFIG))
    def test_positive_profit_across_books(self):
        result=opportunities(event(),config=CONFIG)[0]
        self.assertAlmostEqual(sum(l['stake'] for l in result['legs']),50)
        self.assertGreater(result['profit'],0)
        self.assertEqual(result['payout'],min(l['payout'] for l in result['legs']))
    def test_source_custom_tax_and_override(self):
        quotes=flatten_detail(event(.06),overrides={'a':0})
        self.assertEqual(quotes['1'][0]['tax_rate'],0)
        self.assertEqual(quotes['1'][1]['tax_rate'],.06)
    def test_old_live_and_naive_dates_excluded(self):
        e=event();e['is_live']=True;self.assertFalse(future_event(e,time.time()))
        e['is_live']=False;e['event_date']='2000-01-01T00:00:00+00:00';self.assertFalse(future_event(e,time.time()))
        e['event_date']='2099-01-01T00:00:00';self.assertFalse(future_event(e,time.time()))
    def test_candidate_prefilter(self):self.assertEqual(len(candidate_events([event()],time.time(),slack=0)),1)
    def test_money_rounding(self):
        legs=[{'odds':3.4,'tax_rate':.06,'effective_odds':3.4*.94},{'odds':4.2,'tax_rate':.12,'effective_odds':4.2*.88},{'odds':3.8,'tax_rate':0,'effective_odds':3.8}]
        result=allocate(legs,50.015,CONFIG)
        self.assertEqual(round(sum(l['stake'] for l in result['legs']),2),50.01)
    def test_winning_fee_boundary(self):
        leg={'odds':2,'tax_rate':0}
        self.assertEqual(payout(114000,leg,CONFIG),228000)
        self.assertEqual(payout(114001,leg,CONFIG),205201)
    def test_invalid_source_costs(self):
        with self.assertRaises(ValueError):valid_config({'tax_rate':'bad','winning_tax_rate':.1,'winning_tax_threshold':2280})

class Flow(unittest.TestCase):
    def test_detail_cap_is_visible_as_partial_coverage(self):
        catalogue=[]
        for i in range(12):
            e=event(.12);e['id']=i+1;catalogue.append(e)
        def fetch(path,timeout):return copy.deepcopy(CONFIG if path=='config/' else catalogue)
        def reader(events,deadline,**kwargs):return {e['id']:e for e in events},[]
        with tempfile.TemporaryDirectory() as directory:
            data=run(directory,fetch,reader,fake_notify,env={'DETAIL_LIMIT':'10'})
            self.assertEqual(data['status']['state'],'partial')
            self.assertFalse(data['stats']['candidate_coverage_complete'])
            self.assertEqual(data['stats']['detail_reads'],10)
            self.assertIn('10 z 12',data['status']['message'])
    def test_end_to_end_second_read_confirmation(self):
        with tempfile.TemporaryDirectory() as directory,patch('scan.time.sleep'):
            calls=[]
            def reader(events,deadline,**kwargs):calls.append(events);return {1:event()},[]
            data=run(directory,fake_fetch,reader,fake_notify,env={})
            self.assertEqual(data['status']['state'],'ok')
            self.assertEqual(len(calls),2)
            self.assertEqual(len(data['opportunities']),1)
            self.assertEqual(read(Path(directory)/'web/data/latest.json')['version'],'NEW-1')
    def test_changed_odds_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory,patch('scan.time.sleep'):
            calls=[]
            def reader(events,deadline,**kwargs):
                d=event();calls.append(1)
                if len(calls)==2:
                    for row in d['all_odds']:row['odds']={'1':'1.80','2':'1.80'}
                return {1:d},[]
            data=run(directory,fake_fetch,reader,fake_notify,env={})
            self.assertEqual(data['opportunities'],[])
    def test_confirmation_failure_does_not_send(self):
        with tempfile.TemporaryDirectory() as directory,patch('scan.time.sleep'):
            calls=[];sent=[]
            def reader(events,deadline,**kwargs):
                calls.append(1);return ({1:event()},[]) if len(calls)==1 else ({},['connection failed'])
            def notify(ops,state,**kwargs):sent.extend(ops);return fake_notify(ops,state)
            data=run(directory,fake_fetch,reader,notify,env={})
            self.assertFalse(sent);self.assertFalse(data['opportunities'])
            self.assertEqual(data['status']['state'],'partial')
            self.assertFalse(data['stats']['candidate_coverage_complete'])
    def test_failed_detail_is_retried(self):
        with tempfile.TemporaryDirectory() as directory,patch('scan.time.sleep'):
            calls=[]
            def reader(events,deadline,**kwargs):
                calls.append(1);return ({},['Zdarzenie 1: timeout']) if len(calls)==1 else ({1:event()},[])
            data=run(directory,fake_fetch,reader,fake_notify,env={})
            self.assertEqual(data['status']['state'],'ok')
            self.assertEqual(data['status']['errors'],[])
    def test_provider_failure_preserves_last_success(self):
        with tempfile.TemporaryDirectory() as directory:
            write(Path(directory)/'web/data/latest.json',{'status':{'last_success_at':100},'opportunities':[{'id':'old'}],'events':[]})
            def broken(*args):raise RuntimeError('source unavailable')
            data=run(directory,broken,env={})
            self.assertEqual(data['status']['state'],'error')
            self.assertEqual(data['status']['last_success_at'],100)
            self.assertEqual(data['opportunities'],[])
    def test_wrong_event_id_rejected(self):
        found,errors=details([{'id':1}],time.monotonic()+1,fetch=lambda *args:{'id':2,'all_odds':[]})
        self.assertFalse(found);self.assertTrue(errors)
    def test_keys_do_not_leak_into_public_config(self):
        with tempfile.TemporaryDirectory() as directory:
            config=build(directory,{'SITE_PASSWORD':'private','TELEGRAM_BOT_TOKEN':'secret-bot','ONESIGNAL_API_KEY':'secret-api'})
            text=json.dumps(config)
            self.assertNotIn('private',text);self.assertNotIn('secret-bot',text);self.assertNotIn('secret-api',text)
    def test_missing_password_stops_build(self):
        with tempfile.TemporaryDirectory() as directory,self.assertRaises(RuntimeError):build(directory,{})

class Alerts(unittest.TestCase):
    def test_failure_is_not_marked_sent(self):
        state={};op=opportunities(event(),config=CONFIG)[0]
        result=send_alerts([op],state,send=lambda *args:{'ok':False},env={'TELEGRAM_BOT_TOKEN':'test','TELEGRAM_CHAT_ID':'1'},now=100)
        self.assertEqual(result['accepted'],0)
        self.assertFalse(state['sent'][op['id']].get('last_sent'))
        self.assertTrue(due(state['sent'][op['id']],op['profit_pct'],101))
    def test_service_acceptance_is_recorded(self):
        state={};op=opportunities(event(),config=CONFIG)[0]
        result=send_alerts([op],state,send=lambda *args:{'ok':True},env={'TELEGRAM_BOT_TOKEN':'test','TELEGRAM_CHAT_ID':'1'},now=100)
        self.assertEqual(result['accepted'],1)
        self.assertEqual(state['sent'][op['id']]['last_sent'],100)
        self.assertFalse(due(state['sent'][op['id']],op['profit_pct'],110))
    def test_no_channels_does_not_suppress_future_alert(self):
        state={};op=opportunities(event(),config=CONFIG)[0]
        send_alerts([op],state,env={},now=100)
        self.assertTrue(due(state['sent'][op['id']],op['profit_pct'],110))

if __name__=='__main__':unittest.main()
