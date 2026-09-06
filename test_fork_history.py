"""Forked transcript history must not be billed as new child usage."""
import json
import tempfile
import unittest
from pathlib import Path
import agent_usage as app


def meta(sid,**extra):
    return dict(type='session_meta',payload=dict(id=sid,cwd='/projects/'+sid,**extra))

def context(model):
    return dict(type='turn_context',payload=dict(model=model,turn_id='own-turn'))

def usage(n):
    return dict(timestamp=f'2026-08-25T14:00:{n:02d}Z',type='event_msg',payload=dict(type='token_count',info=dict(
        last_token_usage=dict(input_tokens=100,output_tokens=10),
        total_token_usage=dict(input_tokens=n*100,output_tokens=n*10,total_tokens=n*110))))


class ForkHistoryTests(unittest.TestCase):
    def parse(self,records):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fork.jsonl';p.write_text(''.join(json.dumps(r)+'\n' for r in records))
            return app.parse_codex(p)

    def test_history_is_excluded_and_child_identity_restored(self):
        child=meta('child',forked_from_id='parent',agent_path='/root/child')
        parsed=self.parse([child,usage(1),meta('parent'),usage(2),context('gpt-5.6-sol'),usage(2),usage(3)])
        rows=parsed['requests']
        self.assertEqual(len(rows),2)
        self.assertEqual({r['session'] for r in rows},{'Codex:child'})
        self.assertEqual({r['project'] for r in rows},{'child'})
        self.assertEqual({r['role'] for r in rows},{'subagent'})
        self.assertEqual({r['model'] for r in rows},{'gpt-5.6-sol'})
        self.assertEqual(sum(r['input'] for r in rows),200)
        self.assertEqual(parsed['quality']['codex_fork_history_requests'],2)
        self.assertEqual([r['id'] for r in parsed['sessions']],['Codex:child'])

    def test_foreign_metadata_cannot_take_over_running_fork(self):
        parsed=self.parse([meta('child',forked_from_id='parent'),context('gpt-5.6-sol'),usage(1),
                           meta('parent'),usage(2),meta('child'),context('gpt-5.6-terra'),usage(3)])
        self.assertEqual([r['model'] for r in parsed['requests']],['gpt-5.6-sol','gpt-5.6-sol','gpt-5.6-terra'])
        self.assertEqual({r['session'] for r in parsed['requests']},{'Codex:child'})

    def test_first_own_prompt_telemetry_is_kept(self):
        user=dict(type='response_item',payload=dict(type='message',role='user'))
        start=dict(type='event_msg',payload=dict(type='task_started',turn_id='own-turn'))
        parsed=self.parse([meta('child',forked_from_id='parent'),user,user,usage(1),
                           start,user,context('gpt-5.6-sol'),usage(2)])
        self.assertEqual(len(parsed['requests']),1)
        self.assertEqual(parsed['requests'][0]['trace_stats']['user_messages'],1)

    def test_no_fork_flag_preserves_usage_before_context(self):
        parsed=self.parse([meta('main'),usage(1),context('gpt-5.6-sol'),usage(2)])
        self.assertEqual([r['model'] for r in parsed['requests']],['unknown','gpt-5.6-sol'])
        self.assertNotIn('codex_fork_history_requests',parsed['quality'])

    def test_missing_boundary_keeps_uncertain_records_and_reports_it(self):
        parsed=self.parse([meta('child',forked_from_id='parent'),usage(1),usage(2)])
        self.assertEqual(len(parsed['requests']),2)
        self.assertEqual(parsed['quality']['codex_fork_without_turn_context'],1)
        self.assertEqual({r['model'] for r in parsed['requests']},{'unknown'})


if __name__=='__main__':unittest.main()
