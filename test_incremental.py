"""Incremental collection: what a run may skip, and what it must still produce."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import agent_usage as app

TABLES = ('source_files','sessions','events','event_sources','usage_observations',
          'observation_events','tool_calls','turns','context_snapshots')


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='aisad incremental ')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.home=self.root/'profile';self.output=self.root/'report'

    def write(self,name,events):
        path=self.home/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(''.join(json.dumps(event)+'\n' for event in events))
        return path

    def trace(self,sid='root',second=0,tokens=1000):
        meta=dict(id=sid,cwd='/synthetic/project')
        def event(typ,payload,offset):
            return dict(type=typ,payload=payload,timestamp=f'2026-09-07T10:00:{second+offset:02d}Z')
        return [event('session_meta',meta,0),event('turn_context',dict(model='gpt-5.5',turn_id='turn-1'),1),
                event('response_item',dict(type='function_call',call_id='call-1',name='exec_command',arguments='ARGUMENT'),2),
                event('response_item',dict(type='function_call_output',call_id='call-1',output='RESULT'),3),
                event('event_msg',dict(type='token_count',info=dict(model_context_window=200000,
                    last_token_usage=dict(input_tokens=tokens,cached_input_tokens=500,output_tokens=10),
                    total_token_usage=dict(input_tokens=tokens,output_tokens=10,total_tokens=tokens+10))),4)]

    def args(self,command='collect',*extra):
        return app.parser().parse_args([command,'--home',str(self.home),'--output',str(self.output),
                                        '--timezone','UTC','--to','2026-09-07',*extra])

    def run_command(self,command='collect',*extra):
        return app.make_snapshot(self.args(command,*extra),dashboard=False,include_requests=True)

    def dump(self,path=None):
        path=path or self.output/'sessions.sqlite'
        with contextlib.closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            return {table:sorted(map(repr,db.execute('SELECT * FROM '+table))) for table in TABLES}

    def rebuild_elsewhere(self):
        """The same traces collected into an empty directory: the full-rebuild answer."""
        fresh=self.root/'rebuilt'
        args=app.parser().parse_args(['collect','--home',str(self.home),'--output',str(fresh),
                                      '--timezone','UTC','--to','2026-09-07'])
        app.make_snapshot(args,dashboard=False,include_requests=True)
        return self.dump(fresh/'sessions.sqlite')

    def test_usage_skips_the_evidence_store_and_collect_writes_it(self):
        self.write('.codex/sessions/root.jsonl',self.trace())
        snap=self.run_command('usage')
        self.assertFalse((self.output/'sessions.sqlite').exists())
        self.assertFalse((self.output/'usage.json').exists())
        self.assertEqual(snap['summary']['requests'],1)
        self.assertEqual(snap['session_details'],[])
        self.run_command('collect')
        self.assertTrue((self.output/'sessions.sqlite').exists())
        self.assertTrue((self.output/'usage.json').exists())

    def test_usage_totals_match_a_run_that_also_builds_evidence(self):
        self.write('.codex/sessions/root.jsonl',self.trace())
        self.write('.codex/sessions/other.jsonl',self.trace('other',second=20,tokens=2000))
        fast=app.usage_report(self.run_command('usage'),self.args('usage'))
        full=app.usage_report(self.run_command('collect'),self.args('usage'))
        self.assertEqual(fast['current']['totals'],full['current']['totals'])
        self.assertEqual(fast['current']['rows'],full['current']['rows'])
        self.assertEqual(fast['quality'],full['quality'])

    def test_added_trace_updates_the_store_without_rewriting_untouched_sessions(self):
        self.write('.codex/sessions/root.jsonl',self.trace())
        self.run_command('collect')
        before=self.dump()
        self.write('.codex/sessions/other.jsonl',self.trace('other',second=20,tokens=2000))
        self.run_command('collect')
        after=self.dump()
        self.assertEqual(after,self.rebuild_elsewhere())
        for table in ('events','usage_observations'):
            self.assertTrue(set(before[table]) < set(after[table]),table)

    def test_changed_trace_replaces_its_own_rows_only(self):
        path=self.write('.codex/sessions/root.jsonl',self.trace())
        self.write('.codex/sessions/other.jsonl',self.trace('other',second=20,tokens=2000))
        self.run_command('collect')
        untouched=self.dump()['usage_observations']
        path.write_text(path.read_text()+json.dumps(dict(type='event_msg',timestamp='2026-09-07T10:00:30Z',
            payload=dict(type='token_count',info=dict(model_context_window=200000,
                last_token_usage=dict(input_tokens=7000,cached_input_tokens=0,output_tokens=70),
                total_token_usage=dict(input_tokens=8000,output_tokens=80,total_tokens=8080)))))+'\n')
        self.run_command('collect')
        self.assertEqual(self.dump(),self.rebuild_elsewhere())
        with contextlib.closing(sqlite3.connect(self.output/'sessions.sqlite')) as db:
            rows=db.execute("SELECT count(*),sum(input_tokens) FROM usage_observations WHERE session_id='Codex:root'").fetchone()
        self.assertEqual(rows,(2,8000))
        self.assertTrue(any('Codex:other' in row for row in untouched))

    def test_removed_trace_drops_its_session(self):
        self.write('.codex/sessions/root.jsonl',self.trace())
        removed=self.write('.codex/sessions/other.jsonl',self.trace('other',second=20,tokens=2000))
        self.run_command('collect')
        removed.unlink()
        self.run_command('collect')
        self.assertEqual(self.dump(),self.rebuild_elsewhere())
        with contextlib.closing(sqlite3.connect(self.output/'sessions.sqlite')) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sessions WHERE id='Codex:other'").fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM source_files').fetchone()[0],1)

    def test_new_prices_rewrite_stored_costs_although_no_trace_moved(self):
        self.write('.codex/sessions/root.jsonl',self.trace())
        self.run_command('collect')
        with contextlib.closing(sqlite3.connect(self.output/'sessions.sqlite')) as db:
            first=db.execute('SELECT sum(estimated_cost_usd) FROM usage_observations').fetchone()[0]
        catalog=app.default_prices()
        for entry in catalog['models'].values():
            for field in ('input','output','cache_read','cache_write'):
                if isinstance(entry.get(field),(int,float)):entry[field]=entry[field]*10
        prices=self.root/'prices.json';prices.write_text(json.dumps(catalog))
        snap=self.run_command('collect','--prices',str(prices))
        with contextlib.closing(sqlite3.connect(self.output/'sessions.sqlite')) as db:
            second=db.execute('SELECT sum(estimated_cost_usd) FROM usage_observations').fetchone()[0]
        self.assertGreater(second,first)
        self.assertAlmostEqual(second,snap['summary']['cost'])

    def test_a_combined_cache_row_is_split_rather_than_reparsed(self):
        self.write('.codex/sessions/root.jsonl',self.trace())
        expected=self.run_command('collect')
        cache=self.output/'parse-cache.sqlite'
        with contextlib.closing(sqlite3.connect(cache)) as db:
            rows=db.execute('SELECT path,fingerprint,payload,events FROM parsed').fetchall()
            db.execute('CREATE TABLE files (path TEXT PRIMARY KEY, fingerprint TEXT, payload TEXT)')
            for path,fingerprint,payload,events in rows:
                combined=dict(json.loads(payload),events=json.loads(events))
                db.execute('INSERT INTO files VALUES (?,?,?)',(path,fingerprint,json.dumps(combined)))
            db.execute('DROP TABLE parsed');db.commit()
        snap=self.run_command('collect')
        self.assertEqual(snap['scan'].get('migrated_files'),1)
        self.assertEqual(snap['scan'].get('parsed_files',0),0)
        self.assertEqual(len(snap['events']),len(expected['events']))
        self.assertEqual(snap['summary']['input'],expected['summary']['input'])
        with contextlib.closing(sqlite3.connect(cache)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name='files'").fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM parsed').fetchone()[0],1)

    def test_usage_reads_the_small_cache_column_and_still_sees_every_observation(self):
        self.write('.codex/sessions/root.jsonl',self.trace())
        self.run_command('collect')
        cache=self.output/'parse-cache.sqlite'
        with contextlib.closing(sqlite3.connect(cache)) as db:
            db.execute("UPDATE parsed SET events='not json'");db.commit()
        snap=self.run_command('usage')
        self.assertEqual(snap['summary']['requests'],1)
        self.assertEqual(snap['scan']['cached_files'],1)
        self.assertEqual(snap['scan'].get('parsed_files',0),0)


if __name__=='__main__':unittest.main()
