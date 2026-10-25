"""The same accepted snapshot feeds every local reader, without rescanning."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import agent_usage as app


def snapshot(cost=10):
    day='2026-10-23'
    row=dict(date=day,provider='Claude',model='test',session='Claude:test',
             project='test',role='main',pool='interactive',requests=1,unpriced=0,
             cost=cost,cost_high=cost,input=1,output=1,cached=0,write=0,total=2)
    return dict(version='test',generated=day+'T12:00:00Z',as_of_date=day,
                timezone='System local timezone',rows=[row],
                request_stats=[dict(row,ts=1792756800)],grok_records=[],
                quality={},summary={},history_coverage={})


class SharedUsageTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output=Path(temporary.name)
        self.args=app.parser().parse_args(['chart','--output',str(self.output)])

    def publish(self,cost,revision):
        return app.publish_shared_usage(snapshot(cost),self.args,str(revision).zfill(20))

    def test_canonical_amounts_ignore_display_filters_and_one_off_budget(self):
        self.args.provider='Codex';self.args.monthly_budget=999
        result=self.publish(20,2)
        data=result['snapshot']
        self.assertEqual(data['spend_summary']['periods'][2]['known_cost_usd'],20)
        self.assertEqual(data['spend_summary']['periods'][2]['budget_usd'],2000)
        report=json.loads((self.output/'usage-menubar.json').read_text())
        self.assertEqual(report,data['spend_summary'])
        self.assertEqual(report['sync_revision'],result['revision'])
        for field in ('sources','device','requests','events','source_files'):
            self.assertNotIn(field,data)

    def test_late_collection_cannot_roll_back_any_reader(self):
        newest=self.publish(30,30)
        before=(self.output/app.SHARED_USAGE).read_bytes()
        rejected=self.publish(10,10)
        self.assertEqual(rejected['revision'],newest['revision'])
        self.assertEqual((self.output/app.SHARED_USAGE).read_bytes(),before)
        self.assertIsNone(app.read_shared_usage(self.output,newest['revision']))
        self.assertEqual(json.loads((self.output/'usage-menubar.json').read_text())['periods'][0]['known_cost_usd'],30)

    def test_custom_sources_and_timezone_do_not_publish_global_data(self):
        for key,value in [('timezone','UTC'),('home','/other'),('prices','custom.json'),
                          ('codex_dir','/other'),('managed_session',['Codex:one'])]:
            args=app.parser().parse_args(['chart','--output',str(self.output)])
            setattr(args,key,value)
            self.assertIsNone(app.publish_shared_usage(snapshot(),args))
        self.assertFalse((self.output/app.SHARED_USAGE).exists())

    def test_budget_save_updates_both_read_models_without_collection(self):
        self.publish(20,2)
        with patch.object(app,'make_snapshot',side_effect=AssertionError('unexpected scan')):
            with contextlib.redirect_stdout(io.StringIO()):
                app.main(['budget','--set','100','--output',str(self.output),'--json'])
        state=app.read_shared_usage(self.output)
        native=json.loads((self.output/'usage-menubar.json').read_text())
        chart=app.terminal_chart_report(state['snapshot'],self.args)
        self.assertEqual(native['periods'][2]['budget_usd'],100)
        self.assertEqual(chart['monthly_budget']['budget_usd'],100)
        self.assertEqual(native['periods'][2]['used_percent'],20)
        self.assertEqual(state['snapshot']['generated'],snapshot()['generated'])

    def test_budget_publication_does_not_discard_a_newer_inflight_collection(self):
        self.publish(10,10)
        with contextlib.redirect_stdout(io.StringIO()):
            app.main(['budget','--set','100','--output',str(self.output),'--json'])
        updated=self.publish(30,20)['snapshot']
        self.assertEqual(updated['spend_summary']['periods'][0]['known_cost_usd'],30)
        self.assertEqual(updated['spend_summary']['periods'][2]['budget_usd'],100)

    def test_light_collection_keeps_independent_evidence_timestamp(self):
        source=snapshot()
        source.update(evidence_generated='2026-10-23T10:00:00Z',
                      session_details=[{'id':'test'}],event_previews={'test':[]})
        app.publish_shared_usage(source,self.args,str(1).zfill(20))
        newer=self.publish(25,2)['snapshot']
        self.assertEqual(newer['session_details'],source['session_details'])
        self.assertEqual(newer['evidence_generated'],source['evidence_generated'])
        self.assertEqual(newer['spend_summary']['periods'][0]['known_cost_usd'],25)

    def test_malformed_or_interrupted_publication_keeps_last_complete_state(self):
        self.publish(10,1)
        original=(self.output/app.SHARED_USAGE).read_bytes()
        with patch.object(app,'atom_write',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.publish(20,2)
        self.assertEqual((self.output/app.SHARED_USAGE).read_bytes(),original)
        (self.output/app.SHARED_USAGE).write_text('{broken')
        self.assertIsNone(app.read_shared_usage(self.output))

    def test_failure_before_commit_preserves_prior_accepted_generation(self):
        previous=self.publish(10,1)
        marker=(self.output/'usage-live.js').read_bytes()
        write=app.atom_write
        def interrupted(path,data):
            if path.name=='usage-live.js':raise OSError('interrupted before commit')
            return write(path,data)
        with patch.object(app,'atom_write',side_effect=interrupted):
            with self.assertRaises(OSError):self.publish(20,2)
        self.assertEqual((self.output/'usage-live.js').read_bytes(),marker)
        self.assertEqual(app.read_shared_usage(self.output)['revision'],previous['revision'])
        self.assertEqual(self.publish(30,3)['snapshot']['spend_summary']['periods'][0]['known_cost_usd'],30)

    def test_open_terminal_adopts_external_update_without_scanning(self):
        initial=snapshot(10)
        def ui(found,source,state,color,poll):
            source=Path(source)
            # Another local process publishes the same contract as CLI/menu.
            code="import json,sys;import agent_usage as a;args=a.parser().parse_args(['menubar','--output',sys.argv[1]]);a.publish_shared_usage(json.load(sys.stdin),args,'00000000000000000003')"
            subprocess.run([sys.executable,'-B','-c',code,str(self.output)],
                           input=json.dumps(snapshot(50)),text=True,check=True)
            poll()
            shown=json.loads(source.read_text())
            report=next(x['report'] for x in shown['months'] if x['month']=='2026-10')
            self.assertEqual(report['monthly_budget']['known_cost_usd'],50)
            poll()  # Stable revision does not scan or duplicate work.
            return dict(month='2026-10',view='weeks')
        with patch.object(app,'run_ink',side_effect=ui),patch.object(app,'make_snapshot',side_effect=AssertionError('unexpected scan')):
            result=app.ink_session(('bun',Path('unused')),self.args,False,
                                   app.terminal_ui_dataset(initial,self.args),initial)
        self.assertEqual(result['monthly_budget']['known_cost_usd'],50)


if __name__=='__main__':unittest.main()
