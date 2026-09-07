"""On-demand event provenance and accounting invariants; synthetic files only."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import agent_usage as app


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='aisad evidence ')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.home=self.root/'profile';self.output=self.root/'report'

    def write(self,name,events):
        path=self.home/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(''.join(json.dumps(event)+'\n' for event in events))
        return path

    def args(self,*extra):
        return app.parser().parse_args(['collect','--home',str(self.home),'--output',str(self.output),'--timezone','UTC','--to','2026-09-07',*extra])

    def snapshot(self,*extra):
        return app.make_snapshot(self.args(*extra),dashboard=False,include_requests=True)

    def trace(self,sid='root',parent=None):
        meta=dict(id=sid,cwd='/synthetic/project')
        if parent:meta.update(source={'subagent':{'parent_thread_id':parent}},agent_path='/root/child')
        def event(typ,payload,second):
            return dict(type=typ,payload=payload,timestamp=f'2026-09-07T10:00:{second:02d}Z')
        return [event('session_meta',meta,0),event('turn_context',dict(model='gpt-5.5',turn_id='turn-1'),1),
                event('event_msg',dict(type='task_started',turn_id='turn-1'),2),
                event('response_item',dict(type='function_call',call_id='call-1',name='exec_command',arguments='PRIVATE_ARGUMENT'),3),
                event('response_item',dict(type='function_call_output',call_id='call-1',output='PRIVATE_RESULT'),5),
                event('event_msg',dict(type='token_count',info=dict(model_context_window=200000,
                    last_token_usage=dict(input_tokens=1000,cached_input_tokens=500,output_tokens=10),
                    total_token_usage=dict(input_tokens=1000,output_tokens=10,total_tokens=1010))),6),
                event('response_item',dict(type='function_call',call_id='trailing',name='read_file',arguments='PRIVATE_PATH'),7),
                event('response_item',dict(type='function_call_output',call_id='trailing',output='FINAL_RESULT',is_error=True),9),
                event('event_msg',dict(type='task_complete',turn_id='turn-1'),10),
                event('compacted',dict(message='PRIVATE_SUMMARY'),11)]

    def test_store_reconciles_usage_and_preserves_trailing_events_with_provenance(self):
        path=self.write('.codex/sessions/root.jsonl',self.trace())
        snap=self.snapshot()
        self.assertEqual(snap['summary']['requests'],1)
        detail=snap['session_details'][0]
        self.assertEqual((detail['tool_calls'],detail['tool_results'],detail['tool_errors']),(2,2,1))
        self.assertEqual(detail['status'],'unknown')
        self.assertEqual(detail['last_recorded_lifecycle'],'turn_completed')
        self.assertIsNone(detail['active_seconds'])
        self.assertEqual(detail['elapsed_seconds'],11)
        self.assertEqual(detail['context_since_compaction'],'unavailable')
        self.assertEqual(snap['tool_calls'][0]['observed_latency_seconds'],2)
        event=next(e for e in snap['events'] if e['kind']=='usage');ref=event['evidence'][0]
        with path.open('rb') as source:
            source.seek(ref['byte_offset']);raw=json.loads(source.readline())
        self.assertEqual(app.evidence_id(raw),ref['record_sha256'])
        self.assertEqual(ref['line'],6)
        with contextlib.closing(sqlite3.connect(self.output/'sessions.sqlite')) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],10)
            self.assertEqual(db.execute('SELECT sum(input_tokens) FROM usage_observations').fetchone()[0],snap['summary']['input'])
            self.assertAlmostEqual(db.execute('SELECT sum(estimated_cost_usd) FROM usage_observations').fetchone()[0],snap['summary']['cost'])
            self.assertEqual(db.execute('SELECT context_limit,composition FROM context_snapshots').fetchone(),(200000,'unavailable'))
            self.assertEqual(db.execute('SELECT count(*) FROM observation_events').fetchone()[0],1)
        for file in self.output.iterdir():
            if file.is_file():
                self.assertNotIn(b'PRIVATE_',file.read_bytes())
                self.assertNotIn(b'FINAL_RESULT',file.read_bytes())

    def test_idempotence_copies_append_and_source_deletion(self):
        events=self.trace();path=self.write('.codex/sessions/root.jsonl',events)
        first=self.snapshot();self.assertEqual(len(first['events']),10)
        second=self.snapshot();self.assertEqual(second['scan']['cached_files'],1)
        self.assertEqual(first['events'],second['events'])
        copied=self.write('.codex/archived_sessions/root-copy.jsonl',events)
        copied.write_text('\n'+copied.read_text())
        both=self.snapshot()
        self.assertEqual(len(both['events']),10)
        self.assertEqual(both['summary']['requests'],1)
        self.assertEqual(len(both['events'][0]['evidence']),2)
        copied.unlink();path.unlink();empty=self.snapshot()
        self.assertEqual(empty['events'],[])
        with contextlib.closing(sqlite3.connect(self.output/'sessions.sqlite')) as db:
            for table in ['events','source_files','usage_observations','tool_calls','sessions','context_snapshots']:
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)

    def test_parent_and_tree_totals_never_add_cumulative_reports(self):
        self.write('.codex/sessions/root.jsonl',self.trace())
        self.write('.codex/sessions/child.jsonl',self.trace('child','root'))
        snap=self.snapshot();details={s['id']:s for s in snap['session_details']}
        root=details['Codex:root'];child=details['Codex:child']
        self.assertEqual(root['own']['requests'],1)
        self.assertEqual(root['tree']['requests'],2)
        self.assertEqual(child['parent_session'],'Codex:root')
        self.assertAlmostEqual(root['tree']['known_cost_usd'],snap['summary']['cost'])
        report=app.evidence_report(snap,self.args('--session','Codex:root','--tree','--limit','3'))
        self.assertEqual(len(report['sessions']),2)
        self.assertEqual(len(report['events']),3)
        self.assertEqual(report['next_offset'],3)
        again=app.evidence_report(snap,self.args('--session','Codex:root','--tree','--limit','3','--offset','3'))
        self.assertTrue({e['id'] for e in report['events']}.isdisjoint(e['id'] for e in again['events']))

    def test_claude_copied_streaming_calls_deduplicate_and_event_only_sessions_exist(self):
        events=[dict(type='user',uuid='u1',timestamp='2026-09-07T10:00:00Z',message={'content':'PRIVATE_PROMPT'}),
                dict(type='assistant',uuid='a1',timestamp='2026-09-07T10:00:01Z',message=dict(id='message-1',model='claude-opus-5',
                    usage=dict(input_tokens=10,cache_read_input_tokens=100,cache_creation_input_tokens=20,output_tokens=5),
                    content=[dict(type='tool_use',id='tool-1',name='Read',input={'path':'PRIVATE_PATH'})])),
                dict(type='user',uuid='u2',timestamp='2026-09-07T10:00:02Z',message=dict(content=[dict(type='tool_result',tool_use_id='tool-1',content='PRIVATE_CONTENT')]))]
        self.write('.claude/projects/p/main.jsonl',events+events[1:])
        self.write('.claude/projects/p/copy.jsonl',events)
        self.write('.claude/projects/p/no-usage.jsonl',[dict(type='user',uuid='solo',timestamp='2026-09-07T12:00:00Z',message={'content':'PRIVATE'})])
        snap=self.snapshot()
        self.assertEqual(snap['summary']['requests'],1)
        self.assertEqual(snap['summary']['input'],130)
        self.assertEqual(sum(e['kind']=='tool_call' for e in snap['events']),1)
        self.assertEqual(sum(e['kind']=='tool_result' for e in snap['events']),1)
        no_usage=next(s for s in snap['session_details'] if s['id']=='Claude:no-usage')
        self.assertEqual(no_usage['own']['requests'],0)
        self.assertIsNone(no_usage['own']['estimated_cost_usd'])

    def test_all_time_includes_event_only_dates_and_tool_metrics_respect_window(self):
        events=self.trace()
        events[4]['timestamp']='2026-09-08T10:00:05Z'
        self.write('.codex/sessions/root.jsonl',events)
        self.write('.claude/projects/p/event-only.jsonl',[dict(type='user',uuid='old',timestamp='2026-01-01T00:00:00Z',message={'content':'PRIVATE'})])
        snap=self.snapshot()
        query=self.args('--all-time');query.date_to=None
        report=app.evidence_report(snap,query)
        self.assertEqual(report['period']['from'],'2026-01-01')
        self.assertEqual(report['period']['to'],'2026-09-08')
        self.assertIn('Claude:event-only',{s['id'] for s in report['sessions']})
        report=app.evidence_report(snap,self.args('--session','Codex:root'))
        tool=next(t for t in report['tools'] if t['tool']=='exec_command')
        self.assertEqual((tool['calls'],tool['results'],tool['result_bytes'],tool['timed_calls']),(1,0,0,0))

    def test_no_network_hooks_or_background_process_for_every_command(self):
        self.write('.codex/sessions/root.jsonl',self.trace())
        for command in ['usage','collect','sessions','session','dashboard','statusline']:
            out=io.StringIO()
            args=[command,'--home',str(self.home),'--output',str(self.output),'--to','2026-09-07','--json']
            if command in ['session','statusline']:args+=['--session','Codex:root']
            with contextlib.redirect_stdout(out),patch('socket.socket',side_effect=AssertionError('Network used')),patch('subprocess.Popen',side_effect=AssertionError('Child process used')):
                app.main(args)
            if command!='dashboard':json.loads(out.getvalue())
        self.assertFalse((self.home/'.claude/settings.json').exists())
        self.assertFalse((self.home/'.codex/config.toml').exists())

    def test_missing_result_sizes_and_invalid_timestamps_stay_unknown(self):
        trace=self.trace();trace[4]['payload'].pop('output')
        self.write('.codex/sessions/root.jsonl',trace)
        snap=self.snapshot();report=app.evidence_report(snap,self.args())
        result=next(e for e in report['events'] if e.get('call_id')=='call-1' and e['kind']=='tool_result')
        self.assertIsNone(result['result_bytes'])
        tool=next(t for t in report['tools'] if t['tool']=='exec_command')
        self.assertEqual(tool['results_without_size'],1)
        for value in [True,1e100,float('inf'),float('nan')]:
            self.assertIsNone(app.timestamp(value))

    def test_transaction_rollback_preserves_last_complete_database(self):
        self.write('.codex/sessions/root.jsonl',self.trace());snap=self.snapshot()
        broken=[dict(snap['events'][0],session='missing-session')]
        with self.assertRaises(sqlite3.IntegrityError):
            app.write_event_store(self.output/'sessions.sqlite',snap['source_files'],broken,[],[],[],[],app.default_prices(),'failed')
        with contextlib.closing(sqlite3.connect(self.output/'sessions.sqlite')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],10)
            self.assertEqual(json.loads(db.execute("SELECT value FROM metadata WHERE key='generated'").fetchone()[0]),snap['generated'])


if __name__=='__main__':unittest.main()
