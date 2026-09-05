"""Synthetic fixtures only. Run python3 -m unittest -v test_agent_usage.py."""
import collections
import copy
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import os
import sqlite3
import time
import urllib.request
import urllib.error
import unittest
from unittest.mock import patch
import agent_usage as app

class UsageTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='agent usage test ');self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def file(self,name,rows):
  p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(''.join(json.dumps(r)+'\n' for r in rows));return p
 def row(self,model='claude-opus-5',**kw):
  r=dict(id='cl:one',session='Claude:one',provider='Claude',model=model,ts=1788600000,tier='standard',speed='standard',geo='global',web_searches=0)
  r.update(app.normalize_usage(dict(input_tokens=100,cache_read_input_tokens=1000,cache_creation_input_tokens=200,cache_creation=dict(ephemeral_5m_input_tokens=100,ephemeral_1h_input_tokens=100),output_tokens=50),'Claude'));r.update(kw);return r
 def test_normalization_not_double_counted(self):
  u=app.normalize_usage(dict(input_tokens=1000,cached_input_tokens=900,output_tokens=100,reasoning_output_tokens=70),'Codex')
  self.assertEqual(u['total'],1100);self.assertEqual(u['uncached'],100)
 def test_invalid_counts_are_not_clamped(self):
  with self.assertRaises(ValueError):app.normalize_usage(dict(input_tokens=10,cached_input_tokens=20),'Codex')
  with self.assertRaises(ValueError):app.normalize_usage(dict(input_tokens=-1),'Claude')
 def test_claude_dedup_streaming_and_forks(self):
  a=self.row(role='subagent',project='p');b=dict(a,session='Claude:main',role='main',output=80,total=a['input']+80)
  q=collections.Counter();rs=app.merge_requests([a,b,b],q)
  self.assertEqual(len(rs),1);self.assertEqual(rs[0]['output'],80);self.assertEqual(rs[0]['session'],'Claude:main')
 def test_codex_reset_equal_counter_is_new_request(self):
  def token(ts,n):return dict(type='event_msg',timestamp=ts,payload=dict(type='token_count',info=dict(last_token_usage=dict(input_tokens=n,output_tokens=1),total_token_usage=dict(input_tokens=n,output_tokens=1,total_tokens=n+1))))
  p=self.file('rollout.jsonl',[dict(type='session_meta',payload=dict(id='one',cwd='/work/a')),dict(type='turn_context',payload=dict(model='gpt-5.6-sol')),token('2026-09-01T01:00:00Z',10),token('2026-09-01T01:00:01Z',10),token('2026-09-01T01:00:02Z',20),token('2026-09-01T01:00:03Z',10)])
  result=app.parse_codex(p);self.assertEqual(len(result['requests']),3);self.assertEqual(result['quality']['counter_resets'],1)
 def test_prices_components(self):
  r=self.row();p=app.price_request(r,app.default_prices())
  self.assertAlmostEqual(p['cost'],(100*5+1000*.5+100*6.25+100*10+50*25)/1e6)
 def test_unknown_ttl_range(self):
  r=self.row(write_5m=0,write_1h=0,write_unknown=200)
  p=app.price_request(r,app.default_prices());self.assertGreater(p['cost_high'],p['cost']);self.assertEqual(p['price_status'],'range')
 def test_long_context_fast_geo(self):
  r=self.row('gpt-6-astra',provider='Codex',input=300000,uncached=300000,cached=0,write=0,output=100,write_1h=0,write_5m=0,write_unknown=0,tier='priority',geo='us')
  p=app.price_request(r,app.default_prices());self.assertAlmostEqual(p['cost'],(300000*20+100*75)/1e6*2*1.1)
 def test_unknown_price_is_missing(self):
  p=app.price_request(self.row('new-model'),app.default_prices());self.assertIsNone(p['cost'])
 def test_historical_price_and_gaps(self):
  cat=app.default_prices();rule=cat['models']['claude-opus-5'];cat['models']['claude-opus-5']=[dict(rule,valid_from='2026-10-01')]
  self.assertIsNone(app.price_request(self.row(),cat)['cost'])
 def test_custom_prices_utf8(self):
  cat=app.default_prices();cat['note']='Local rates — USD'
  p=self.root/'prices.json';p.write_text(json.dumps(cat,ensure_ascii=False),encoding='utf-8')
  self.assertEqual(app.load_prices(p)['note'],cat['note'])
 def test_billing_duplicate_rejected_and_credit_preserved(self):
  p=self.root/'billing.csv';p.write_text('transaction_id,date,provider,amount_usd\none,2026-09-01,Claude,-5\n')
  self.assertEqual(app.read_billing(p)[0]['amount'],-5)
  p.write_text(p.read_text()+'one,2026-09-01,Claude,1\n')
  with self.assertRaises(ValueError):app.read_billing(p)
 def test_partial_jsonl(self):
  p=self.file('active.jsonl',[dict(type='valid')]);p.write_bytes(p.read_bytes()+b'{"type":')
  q=collections.Counter();self.assertEqual(len(list(app.read_jsonl(p,q))),1);self.assertEqual(q['partial_tail'],1)
 def test_empty_profile_and_output_spaces(self):
  args=app.parser().parse_args(['--home',str(self.root/'fresh user'),'--output',str(self.root/'out folder')])
  with patch('socket.socket',side_effect=AssertionError('network used')):
   d=app.make_snapshot(args)
  self.assertEqual(d['summary']['requests'],0);self.assertTrue((self.root/'out folder/dashboard.html').exists())
 def test_cache_reuse_append_and_deletion(self):
  msg=dict(type='assistant',timestamp='2026-09-01T00:00:00Z',message=dict(id='first',model='claude-opus-5',usage=dict(input_tokens=100,output_tokens=10)))
  p=self.file('fresh/.claude/projects/project/one.jsonl',[msg]);args=app.parser().parse_args(['--home',str(self.root/'fresh'),'--output',str(self.root/'out')])
  a=app.make_snapshot(args);b=app.make_snapshot(args);self.assertEqual(a['summary']['requests'],1);self.assertEqual(b['scan']['cached_files'],1)
  msg['message']['id']='second';p.write_text(p.read_text()+json.dumps(msg)+'\n');self.assertEqual(app.make_snapshot(args)['summary']['requests'],2)
  p.unlink();self.assertEqual(app.make_snapshot(args)['summary']['requests'],0)
 def test_date_suffix(self):self.assertEqual(app.canonical_model('claude-sonnet-4-5-20250929'),'claude-sonnet-4-5')
 def test_safe_html_payload(self):
  payload=dict(title='</script><img src=x onerror=alert(1)>');html=app.render_html(payload);embedded=html.split('<script id="snapshot" type="application/json">')[1].split('</script>')[0]
  self.assertNotIn('<',embedded);self.assertEqual(json.loads(embedded),payload)

 def test_registry_schema_and_nondefault_home(self):
  root=self.root/'alternate user';cx=root/'.codex';cx.mkdir(parents=True)
  db=sqlite3.connect(cx/'state_4.sqlite');db.execute('CREATE TABLE threads(id TEXT, model TEXT, cwd TEXT)');db.execute("INSERT INTO threads VALUES ('test-id','gpt-5.5','/projects/example')");db.commit();db.close()
  args=app.parser().parse_args(['--home',str(root),'--output',str(self.root/'out')])
  with patch.dict(os.environ,{'CODEX_HOME':'/should/not/read','CLAUDE_CONFIG_DIR':'/should/not/read'}):
   d=app.make_snapshot(args)
  self.assertEqual(d['summary']['registry_codex'],1);self.assertEqual(d['summary']['requests'],0)
 def test_copied_single_file_isolated_python(self):
  copied=self.root/'tool folder'/'agent_usage.py';copied.parent.mkdir();copied.write_text(Path(app.__file__).read_text(encoding='utf-8'),encoding='utf-8')
  run=subprocess.run([sys.executable,'-I',str(copied),'--home',str(self.root/'empty'),'--output',str(self.root/'out')],capture_output=True,text=True)
  self.assertEqual(run.returncode,0,run.stderr);self.assertTrue((self.root/'out/dashboard.html').is_file())
 def test_loopback_watcher_updates_and_hides_evidence(self):
  msg=dict(type='assistant',timestamp='2026-09-01T00:00:00Z',message=dict(id='a',model='claude-opus-5',usage=dict(input_tokens=10,output_tokens=2)))
  trace=self.file('profile/.claude/projects/p/s.jsonl',[msg]);out=self.root/'watch out'
  process=subprocess.Popen([sys.executable,str(Path(app.__file__).resolve()),'--home',str(self.root/'profile'),'--output',str(out),'--watch','5'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  try:
   url=None
   for _ in range(4):
    line=process.stdout.readline()
    if line.startswith('http://127.0.0.1:'):url=line.split(' ')[0];break
   self.assertIsNotNone(url)
   def status():
    with urllib.request.urlopen(url+'status.json',timeout=3) as response:return json.load(response)['generated']
   initial=status()
   with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(url+'usage.json')
   self.assertEqual(error.exception.code,404)
   error.exception.close()
   msg['message']['id']='b';trace.write_text(trace.read_text()+json.dumps(msg)+'\n')
   deadline=time.monotonic()+12;updated=False
   while time.monotonic()<deadline:
    time.sleep(.25)
    if status()!=initial:updated=True;break
   self.assertTrue(updated);self.assertEqual(json.loads((out/'usage.json').read_text(encoding='utf-8'))['summary']['requests'],2)
  finally:
   process.terminate();process.communicate(timeout=5)

if __name__=='__main__':unittest.main()
