"""Regression evidence for resumed sessions and supplemental Grok accounting."""
import collections
import json
import tempfile
import unittest
from pathlib import Path
import agent_usage as app

class HistoryAuditTests(unittest.TestCase):
    def test_resumed_session_keeps_known_model_but_new_session_does_not(self):
        rows=[]
        def meta(sid,**extra):rows.append(dict(type='session_meta',payload=dict(id=sid,**extra)))
        def context(model):rows.append(dict(type='turn_context',payload=dict(model=model)))
        def token(n):rows.append(dict(timestamp='2026-09-01T00:00:%02dZ'%n,type='event_msg',payload=dict(type='token_count',info=dict(last_token_usage=dict(input_tokens=10,output_tokens=1),total_token_usage=dict(input_tokens=10*n,output_tokens=n,total_tokens=11*n)))))
        meta('a');token(1);context('gpt-5.6-sol');token(2);meta('a');token(3)
        context('gpt-5.6-terra');meta('a');token(4);meta('b');token(5)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'trace.jsonl';p.write_text(''.join(json.dumps(x)+'\n' for x in rows));r=app.parse_codex(p)['requests']
        self.assertEqual([x['model'] for x in r],['unknown','gpt-5.6-sol','gpt-5.6-sol','gpt-5.6-terra','unknown'])
        self.assertEqual(sum(x['input'] for x in r),50)

    def test_current_rates_apply_equally_to_old_and_new_dates(self):
        cat=app.default_prices();self.assertEqual(cat['basis'],'current_rates')
        r=dict(model='gpt-5.6-sol',provider='Codex',tier='standard',geo='global',**app.normalize_usage(dict(input_tokens=10000,cached_input_tokens=8000,output_tokens=100),'Codex'))
        costs=[app.price_request(dict(r,ts=app.timestamp(date)),cat)['cost'] for date in ['2024-01-01','2026-07-15','2026-09-05']]
        self.assertEqual(costs,[.0132]*3)

    def test_grok_turns_are_deduped_and_keep_incomplete_reported_cost_separate(self):
        def row(pid,ticks):
            u=dict(inputTokens=100,cachedReadTokens=80,outputTokens=20,modelCalls=2,modelUsage={'grok-4.6-build':{}})
            if ticks is not None:u['costUsdTicks']=ticks
            return dict(timestamp=1788510975,params=dict(sessionId='one',update=dict(sessionUpdate='turn_completed',prompt_id=pid,usage=u)))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'.grok/sessions/project/one/updates.jsonl';p.parent.mkdir(parents=True);p.write_text('\n'.join(json.dumps(r) for r in [row('a',10000000000),row('a',10000000000),row('b',None)]))
            args=app.parser().parse_args(['--home',d]);records=app.grok_usage(args,collections.Counter())
        total=app.grok_totals(records)
        self.assertEqual((total['turns'],total['model_calls'],total['known_reported_cost_usd'],total['incomplete_turns']),(2,4,1,1))
        self.assertFalse(total['included_in_api_estimate'])
        self.assertIsNone(records[1]['reported_cost_usd'])

if __name__=='__main__':unittest.main()
