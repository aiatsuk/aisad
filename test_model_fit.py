"""Model fit: capture, classes, verdicts, events and the fit / suggest commands.

Synthetic profiles in temporary directories only; HOME points at the profile.
Run python3 -m unittest -v test_model_fit.
"""
import collections
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agent_usage as app

ROOT = Path(__file__).resolve().parent
PROMPT_MARK = 'zebracorn'          # appears only in prompt text
PATH_MARK = 'privatefolderxyz'     # appears only in edited file paths

# The snapshot contract documented in the plan ("Snapshot contract (for step 3)").
CONTRACT_TOP = {'schema', 'guide', 'units', 'events', 'note'}
CONTRACT_GUIDE = {'class', 'label', 'tier', 'effort', 'effort_max', 'why'}
CONTRACT_UNIT = {'kind', 'session', 'main_session', 'n', 'project', 'date', 'ts', 'tier', 'model', 'effort', 'class',
                 'signals', 'rec_tier', 'rec_effort', 'rec_effort_max', 'verdict', 'effort_over', 'cost', 'unpriced',
                 'save_model', 'save_effort', 'calls', 'agent_type', 'explicit_model'}
CONTRACT_EVENTS = {'switches': {'session', 'project', 'date', 'ts', 'from', 'to', 'tokens', 'cost'},
                   'cold': {'session', 'project', 'date', 'ts', 'gap_min', 'model', 'tokens', 'cost'},
                   'effort_changes': {'session', 'project', 'date', 'ts', 'from', 'to', 'read_share'},
                   'daily': {'date', 'project', 'calls', 'cost', 'big_calls', 'big_cost', 'haiku_long_calls',
                             'haiku_long_cost', 'fast_calls', 'fast_cost'}}


def assistant(mid, model='claude-opus-5-5', ts='2026-11-01T10:00:00.000Z', effort='high', tools=(), first=0,
              inp=10, cw=0, cw1h=0, read=1000, out=100, speed='standard', cwd='/work/demo-proj'):
    content = [{'type': 'tool_use', 'id': f'tu_{mid}_{first + i}', 'name': name, 'input': args}
               for i, (name, args) in enumerate(tools)] or [{'type': 'text', 'text': 'ok'}]
    record = {'type': 'assistant', 'timestamp': ts, 'cwd': cwd,
              'message': {'id': mid, 'model': model, 'role': 'assistant', 'content': content,
                          'usage': {'input_tokens': inp, 'cache_creation_input_tokens': cw,
                                    'cache_read_input_tokens': read, 'output_tokens': out, 'speed': speed,
                                    'cache_creation': {'ephemeral_1h_input_tokens': cw1h,
                                                       'ephemeral_5m_input_tokens': cw - cw1h}}}}
    if effort:
        record['effort'] = effort
    return record


def human(text, ts='2026-11-01T09:59:00.000Z', cwd='/work/demo-proj'):
    return {'type': 'user', 'timestamp': ts, 'origin': {'kind': 'human'}, 'cwd': cwd,
            'message': {'role': 'user', 'content': text}}


def tool_result(ts='2026-11-01T10:00:30.000Z'):
    return {'type': 'user', 'timestamp': ts, 'sourceToolAssistantUUID': 'x', 'toolUseResult': {'a': 1},
            'message': {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 't', 'content': 'r'}]}}


def write_jsonl(path, records, tail=''):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r) + '\n' for r in records) + tail, encoding='utf-8')


def unit(**kw):
    """A folded unit as fit_unit returns it, for the classifier and the judge."""
    base = {'kind': 'turn', 'session': 'Claude:s', 'main_session': 'Claude:s', 'n': 1, 'project': 'p',
            'date': '2026-11-01', 'ts': 1793527200.0, 'calls': 5, 'n_files': 0, 'n_tools': 4, 'n_agents': 0,
            'workflow': False, 'n_web': 0, 'n_ui': 0, 'docs_only': False, 'model': 'claude-opus-5-5',
            'effort': 'high', 'cost': 10.0, 'unpriced': 0,
            'alt': {'haiku': 0.3, 'sonnet': 5.0, 'opus': 10.0, 'fable': 20.0},
            'by_model': {'claude-opus-5-5': 10.0}, 'by_effort': {'high': 10.0}, 'requests': [],
            'agent_type': None, 'explicit_model': None}
    for text_key in ('prompt', 'desc'):
        text = kw.pop(text_key, None)
        if text:
            base.update(app.fit_text_flags(text))
    if base['kind'] == 'agent' or kw.get('kind') == 'agent':
        base.update(app.fit_agent_flags(kw.get('agent_type') or 'unknown', kw.pop('label', ''), ''))
    base.update(kw)
    return base


class FitCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='asi fit test ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / 'profile'
        self.output = self.root / 'out'
        self.projects = self.home / '.claude/projects'
        self.projects.mkdir(parents=True)
        environment = patch.dict(os.environ, {'HOME': str(self.home)})
        environment.start()
        self.addCleanup(environment.stop)
        for name in ('CLAUDE_SESSION_ID', 'CLAUDE_CONFIG_DIR', 'CODEX_HOME'):
            os.environ.pop(name, None)

    def session(self, records, name='s1', project='-work-demo-proj', tail=''):
        path = self.projects / project / f'{name}.jsonl'
        write_jsonl(path, records, tail)
        return path

    def agent(self, main, name, records, meta=None, workflow=None):
        folder = main.with_suffix('') / 'subagents'
        if workflow:
            folder = folder / 'workflows' / workflow
        path = folder / f'agent-{name}.jsonl'
        write_jsonl(path, records)
        if meta is not None:
            (folder / f'agent-{name}.meta.json').write_text(meta if isinstance(meta, str) else json.dumps(meta))
        return path

    def argv(self, command, *extra):
        return [command, '--home', str(self.home), '--output', str(self.output), '--timezone', 'UTC', *extra]

    def snapshot(self, *extra, command='fit'):
        return app.make_snapshot(app.parser().parse_args(self.argv(command, *extra)), dashboard=False, include_requests=True)

    def run_main(self, command, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            app.main(self.argv(command, *extra))
        return out.getvalue()

    def fit_json(self, *extra):
        return json.loads(self.run_main('fit', '--json', *extra))

    def cli(self, command, *extra, cwd=None, env=None):
        environment = dict(os.environ, HOME=str(self.home))
        environment.pop('CLAUDE_SESSION_ID', None)
        environment.update(env or {})
        return subprocess.run([sys.executable, str(ROOT / 'agent_usage.py'), *self.argv(command, *extra)],
                              capture_output=True, text=True, env=environment, cwd=cwd or self.root)

    def refusal(self, command, *extra):
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stdout(io.StringIO()):
            app.main(self.argv(command, *extra))
        return str(caught.exception.code)

    def bundle(self):
        """One main session with two turns, a spawned Explore run and a workflow agent."""
        main = self.session([
            human(f'do the thing {PROMPT_MARK}'),
            assistant('m1', tools=[('Agent', {'subagent_type': 'Explore', 'model': 'haiku', 'prompt': 'p'})]),
            tool_result(),
            assistant('m2', ts='2026-11-01T10:01:00.000Z',
                      tools=[('Edit', {'file_path': f'/Users/someone/{PATH_MARK}/x.py'})]),
            human('thanks', ts='2026-11-01T10:05:00.000Z'),
            assistant('m3', ts='2026-11-01T10:05:10.000Z'),
        ])
        self.agent(main, 'a1', [human('find files'), assistant('s1', model='claude-haiku-5-5', effort='medium',
                                                               ts='2026-11-01T10:00:20.000Z')],
                   meta={'agentType': 'Explore', 'description': f'find {PROMPT_MARK}', 'toolUseId': 'tu_m1_0'})
        self.agent(main, 'b2', [human('step'), assistant('w1', ts='2026-11-01T10:02:00.000Z')], workflow='wf_1')
        return main


class CaptureTests(FitCase):
    def test_blocks_of_one_reply_share_their_facts_and_are_counted_once(self):
        path = self.session([human('fix it'),
                             assistant('m1', out=5, tools=[('Read', {'file_path': '/a'})]),
                             tool_result(),
                             assistant('m1', out=250, tools=[('Edit', {'file_path': '/a.py'})], first=1),
                             assistant('m1', out=250, tools=[('Edit', {'file_path': '/a.py'})], first=1)])
        parsed = app.parse_claude(path)
        self.assertEqual(len(parsed['requests']), 3)                 # merged later, as before
        facts = parsed['requests'][0]['fit']
        self.assertEqual((facts['turn'], facts['tools'], len(facts['files'])), (1, 2, 1))
        self.assertTrue(all(r['fit'] is facts for r in parsed['requests']))
        snap = self.snapshot('--all-time')
        self.assertEqual([r['output'] for r in snap['requests']], [250])
        [turn] = snap['fit_analysis']['units']
        self.assertEqual((turn['calls'], turn['n_tools'], turn['n_files']), (1, 2, 1))

    def test_file_paths_are_kept_as_short_hashes_with_a_document_flag(self):
        path = self.session([human('q'), assistant('m1', tools=[('Write', {'file_path': f'/{PATH_MARK}/notes.md'}),
                                                               ('NotebookEdit', {'notebook_path': f'/{PATH_MARK}/n.ipynb'})])])
        files = app.parse_claude(path)['requests'][0]['fit']['files']
        self.assertEqual([doc for _, doc in files], [1, 0])
        self.assertTrue(all(len(digest) == 12 for digest, _ in files))
        self.assertNotIn(PATH_MARK, json.dumps(app.parse_claude(path)))

    def test_human_turn_detection(self):
        records = [
            human('<system-reminder>ctx</system-reminder>\nreal question'),
            human('<command-name>/asi-suggest</command-name><command-args>now</command-args>'),
            human('<task-notification>done</task-notification>'),
            {'type': 'user', 'isMeta': True, 'message': {'content': 'meta'}},
            {'type': 'user', 'origin': {'kind': 'agent'}, 'message': {'content': 'from an agent'}},
            {'type': 'user', 'isCompactSummary': True, 'message': {'content': 'summary'}},
            {'type': 'user', 'message': {'content': [{'type': 'text', 'text': 'typed in blocks'}]}},
            tool_result(),
            assistant('m1'),
        ]
        path = self.session(records)
        fit = app.parse_claude(path, include_titles=True)['fit']
        self.assertEqual([t['title'] for t in fit['turns']], ['real question', '/asi-suggest now', 'typed in blocks'])
        self.assertNotIn('title', json.dumps(app.parse_claude(path)['fit']))
        self.assertEqual(app.parse_claude(path)['requests'][0]['fit']['turn'], 3)

    def test_keyword_flags_follow_the_prompt(self):
        path = self.session([human('please refactor the store'), assistant('m1'), human('why does it crash?'),
                             assistant('m2', ts='2026-11-01T10:01:00.000Z'), human('thanks'),
                             assistant('m3', ts='2026-11-01T10:02:00.000Z')])
        turns = app.parse_claude(path)['fit']['turns']
        self.assertEqual([(t.get('big', 0), t.get('hard', 0)) for t in turns], [(1, 0), (0, 1), (0, 0)])

    def test_torn_tail_synthetic_and_missing_usage_are_skipped(self):
        synthetic = assistant('m2', model='<synthetic>')
        no_usage = {'type': 'assistant', 'message': {'id': 'm3', 'model': 'claude-opus-5-5', 'content': []}}
        self.session([human('q'), assistant('m1'), synthetic, no_usage], tail='{"type":"assistant","mess')
        snap = self.snapshot('--all-time')
        self.assertEqual([u['calls'] for u in snap['fit_analysis']['units']], [1])
        self.assertEqual(snap['quality']['partial_tail'], 1)

    def test_odd_record_shapes_cost_one_record_not_the_session(self):
        def broken(name, **patch_):
            record = assistant(name, tools=[('Edit', {'file_path': '/a'})])
            record['message']['usage'].update(patch_)
            return record
        weird = assistant('w1', tools=[('Edit', {'file_path': ['/x']}), (7, {}), ('Read', 'not a dict')])
        records = [human('q'), assistant('ok'),
                   {'type': 'assistant', 'message': 'a string'},
                   broken('b1', cache_creation='nope'),                    # used to fail the whole file
                   broken('b2', server_tool_use=['x']),                    # used to fail the whole file
                   broken('b3', input_tokens='abc'),
                   assistant('b4', tools=[('Read', {})], first=0),
                   {'type': 'user', 'message': 'assistant text'},
                   {'type': 'user', 'message': {'content': [{'type': 'text', 'text': None}]}},
                   {'type': 'user', 'message': {'content': 7}},
                   {'type': 'assistant', 'timestamp': 12345, 'message': {
                       'id': 'u1', 'model': 'claude-opus-5-5', 'content': [{'type': 'tool_use', 'id': ['unhashable']}],
                       'usage': {'input_tokens': 1, 'output_tokens': 1}}},
                   weird]
        path = self.session(records, tail='"assistant"\n["assistant"]\n')
        for titles in (False, True):
            parsed = app.parse_claude(path, include_titles=titles)
            ids = [r['id'] for r in parsed['requests']]
            self.assertEqual(ids, ['cl:ok', 'cl:b4', 'cl:w1'])
            self.assertEqual(parsed['quality']['invalid_usage'], 2)                  # b1 and b3
            self.assertEqual(parsed['quality']['invalid_records'], 2)                # b2 and the unhashable tool id
            weird_fit = next(r['fit'] for r in parsed['requests'] if r['id'] == 'cl:w1')
            self.assertEqual((weird_fit['tools'], weird_fit.get('files', [])), (2, []))
        # A session title is read from the first user records, which used to fail the file on odd content.
        titled = self.session([{'type': 'user', 'message': {'content': [{'type': 'text', 'text': None}]}},
                               {'type': 'user', 'message': {'content': 7}}, human('q'), assistant('t1')], name='titled')
        parsed = app.parse_claude(titled, include_titles=True)
        self.assertEqual(([r['id'] for r in parsed['requests']], parsed['quality']['invalid_records']), (['cl:t1'], 2))
        self.assertEqual(parsed['sessions'][0]['title'], 'q')
        snap = self.snapshot('--all-time')
        self.assertNotIn('failed_files', snap['quality'])
        self.assertEqual(sum(u['calls'] for u in snap['fit_analysis']['units']), len(snap['requests']))

    def test_subagent_meta_and_explicit_model(self):
        main = self.session([human('go'),
                             assistant('m1', tools=[('Agent', {'subagent_type': 'Explore', 'model': 'haiku'}),
                                                    ('Task', {'subagent_type': 'general-purpose'})])])
        self.agent(main, 'a1', [human('look'), assistant('s1', model='claude-haiku-5-5')],
                   meta={'agentType': 'Explore', 'description': 'find files', 'toolUseId': 'tu_m1_0'})
        self.agent(main, 'a2', [human('fix'), assistant('s2', model='claude-sonnet-5-5')],
                   meta={'agentType': 'general-purpose', 'model': 'sonnet', 'toolUseId': 'tu_m1_9'})
        self.agent(main, 'a3', [human('plan'), assistant('s3')],
                   meta={'agentType': 'Plan', 'description': 'Review the plan', 'toolUseId': 'tu_m1_1'})
        agents = {u['session']: u for u in self.snapshot('--all-time')['fit_analysis']['units'] if u['kind'] == 'agent'}
        self.assertEqual({k: (u['agent_type'], u['explicit_model']) for k, u in agents.items()},
                         {'Claude:s1/agent-a1': ('Explore', True), 'Claude:s1/agent-a2': ('general-purpose', True),
                          'Claude:s1/agent-a3': ('Plan', False)})
        self.assertEqual(agents['Claude:s1/agent-a3']['class'], 'architect')
        self.assertTrue(agents['Claude:s1/agent-a3']['review'])
        self.assertEqual({u['main_session'] for u in agents.values()}, {'Claude:s1'})

    def test_workflow_agents_get_their_real_parent_without_changing_rows(self):
        self.bundle()
        snap = self.snapshot('--all-time')
        workflow = next(u for u in snap['fit_analysis']['units'] if u['session'] == 'Claude:workflows/agent-b2')
        self.assertEqual(workflow['main_session'], 'Claude:s1')
        self.assertTrue(workflow['workflow_agent'])
        self.assertEqual(workflow['agent_type'], 'unknown')
        self.assertFalse(workflow['explicit_model'])
        row = next(r for r in snap['requests'] if r['session'] == 'Claude:workflows/agent-b2')
        self.assertEqual(row['parent_session'], 'Claude:workflows')          # the existing field stays as it was
        self.assertIn('Claude:workflows/agent-b2', {r['session'] for r in snap['rows']})
        entry = snap['fit_analysis']['sessions']['Claude:s1']
        self.assertEqual(sorted(u['kind'] for u in entry['units']), ['agent', 'agent', 'turn', 'turn'])

    def test_bad_meta_files_are_tolerated_and_counted(self):
        main = self.session([human('q'), assistant('m1')])
        for i, meta in enumerate(('[]', 'null', '{half', '{"agentType": 5, "toolUseId": ["x"], "description": {"a": 1}}')):
            self.agent(main, f'a{i}', [human('p'), assistant(f's{i}')], meta=meta)
        self.agent(main, 'nometa', [human('p'), assistant('s9')])
        snap = self.snapshot('--all-time')
        agents = [u for u in snap['fit_analysis']['units'] if u['kind'] == 'agent']
        self.assertEqual([u['agent_type'] for u in agents], ['unknown'] * 5)
        self.assertEqual(snap['quality']['fit_unreadable_meta'], 3)

    def test_calls_before_the_first_prompt_form_turn_zero(self):
        self.session([assistant('m0'), human('next', ts='2026-11-01T10:01:00.000Z'),
                      assistant('m1', ts='2026-11-01T10:02:00.000Z')])
        units = self.snapshot('--all-time')['fit_analysis']['units']
        self.assertEqual([(u['n'], u['title'] if not u['n'] else None) for u in units],
                         [(0, '(resumed without a new prompt)'), (1, None)])
        self.session([assistant('x0')], name='bare')
        bare = [u for u in self.snapshot('--all-time')['fit_analysis']['units'] if u['session'] == 'Claude:bare']
        self.assertEqual(bare[0]['title'], '(no prompt recorded)')

    def test_copied_replies_keep_the_owner_turn_and_every_tool_call(self):
        owner = {'turn': 2, 'tools': 1, 'files': [['aaa', 0]]}
        other = {'turn': 5, 'tools': 3, 'files': [['bbb', 1], ['aaa', 0]], 'spawn_models': {'t1': 'haiku'}, 'effort': 'low'}
        merged = app.fit_merge(owner, other)
        self.assertEqual((merged['turn'], merged['tools'], merged['files'], merged['spawn_models'], merged['effort']),
                         (2, 3, [['aaa', 0], ['bbb', 1]], {'t1': 'haiku'}, 'low'))
        self.assertIsNone(app.fit_merge(None, other))       # owned by a trace model fit does not read
        main = self.session([human('q'), assistant('m1', tools=[('Read', {})])], name='aaa-main')
        fork = self.session([human('q'), assistant('m1', tools=[('Read', {}), ('Grep', {})]),
                             human('more'), assistant('m2', ts='2026-11-01T10:03:00.000Z')], name='bbb-fork')
        self.assertTrue(main.exists() and fork.exists())
        snap = self.snapshot('--all-time')
        first = next(u for u in snap['fit_analysis']['units'] if 'cl:m1' in [r['id'] for r in u['requests']])
        self.assertEqual((first['session'], first['n_tools']), ('Claude:aaa-main', 2))
        self.assertEqual(snap['quality']['cross_session_copies'], 1)

    def test_fit_facts_survive_the_parse_cache(self):
        self.bundle()
        cold = self.snapshot('--all-time')
        warm = self.snapshot('--all-time')
        self.assertGreater(warm['scan']['cached_files'], 0)
        self.assertEqual(cold['model_fit'], warm['model_fit'])
        self.assertEqual(warm['scan'].get('parsed_files', 0), 0)

    def test_existing_usage_outputs_are_unchanged_by_the_capture(self):
        self.bundle()
        with_fit = self.snapshot('--all-time', command='usage')
        self.output = self.root / 'out-without'
        with patch.object(app, 'FitCapture', lambda *a: None):
            without = self.snapshot('--all-time', command='usage')
        for key in ('rows', 'summary', 'request_stats', 'quality'):
            self.assertEqual(with_fit[key], without[key], key)
        self.assertEqual(with_fit['requests'], without['requests'])
        self.assertTrue(all('fit' not in r for r in with_fit['requests']))
        args = app.parser().parse_args(self.argv('usage', '--all-time', '--include-requests'))
        self.assertEqual(json.dumps(app.usage_report(with_fit, args)['current'], sort_keys=True),
                         json.dumps(app.usage_report(without, args)['current'], sort_keys=True))
        self.assertEqual(without['model_fit']['units'], [])
        usage = json.loads(self.run_main('usage', '--json', '--all-time', '--include-requests'))
        self.assertTrue(all('fit' not in r for r in usage['current']['requests']))


class ClassTests(unittest.TestCase):
    def test_classes(self):
        cases = [
            (unit(calls=2, n_tools=1), 'chat'),
            (unit(calls=20), 'investigate'),
            (unit(calls=60), 'everyday'),
            (unit(n_files=2, calls=20), 'scoped'),
            (unit(n_files=2, calls=20, prompt='debug the flaky test'), 'everyday'),
            (unit(n_files=2, calls=20, docs_only=True), 'docs'),
            (unit(n_files=2, calls=90, docs_only=True), 'everyday'),
            (unit(n_files=12, calls=90), 'architect'),
            (unit(n_files=5, calls=30, prompt='migrate the store'), 'architect'),
            (unit(n_agents=6), 'lead'),
            (unit(workflow=True), 'lead'),
            (unit(calls=200, n_files=3), 'lead'),
            (unit(n_web=9), 'research'),
            (unit(n_ui=8, n_tools=10), 'vision'),
            (unit(kind='agent', agent_type='Explore', calls=30), 'lookup'),
            (unit(kind='agent', agent_type='workflow-subagent', label='dispatch:x', calls=2), 'lookup'),
            (unit(kind='agent', agent_type='orchestrate-reviewer', label='Review diff', calls=30), 'investigate'),
            (unit(kind='agent', agent_type='general-purpose', n_web=9), 'research'),
            (unit(kind='agent', agent_type='general-purpose', n_files=2, calls=20), 'scoped'),
            (unit(kind='agent', agent_type='general-purpose', n_files=2, calls=20, prompt='fix the crash'), 'everyday'),
            (unit(kind='agent', agent_type='general-purpose', n_files=1, docs_only=True), 'docs'),
            (unit(kind='agent', agent_type='general-purpose', n_files=6, calls=80), 'everyday'),
            (unit(kind='agent', agent_type='general-purpose', calls=60), 'everyday'),
            (unit(kind='agent', agent_type='Plan', calls=8), 'architect'),
        ]
        for u, want in cases:
            self.assertEqual(app.fit_classify(u)[0], want, u)

    def test_a_short_subagent_run_is_not_lookup_by_itself(self):
        for calls in (1, 3, 4):
            self.assertEqual(app.fit_classify(unit(kind='agent', agent_type='general-purpose', calls=calls))[0], 'investigate')

    def test_every_class_has_a_valid_recommendation(self):
        for cid in app.FIT_CLASSES:
            r = app.fit_rec(cid)
            self.assertIn(r['tier'], app.FIT_TIERS)
            self.assertIn(r['model'], app.default_prices()['models'])
            self.assertLessEqual(app.fit_erank(r['effort']), app.fit_erank(r['effort_max']))
        self.assertEqual([g['class'] for g in app.fit_guide()], list(app.FIT_CLASSES))

    def test_flags_from_text(self):
        self.assertEqual(app.fit_text_flags('Please REFACTOR and debug'), {'big': 1, 'hard': 1})
        self.assertEqual(app.fit_text_flags('переработать модуль'), {'big': 1})
        self.assertEqual(app.fit_agent_flags('Plan', 'collect notes'), {'plan': 1, 'relay': 1})
        self.assertEqual(app.fit_agent_flags('orchestrate-reviewer'), {'review': 1})
        self.assertEqual(app.fit_tier('claude-opus-5-5[1m]'), 'opus')
        self.assertIsNone(app.fit_tier('gpt-6-sol'))


class JudgeTests(unittest.TestCase):
    def test_over_and_effort_savings(self):
        j = app.fit_judge(unit(calls=20, effort='xhigh'))            # investigate -> sonnet/medium
        self.assertEqual(j['verdict'], 'over')
        self.assertAlmostEqual(j['save_model'], 5.0)
        self.assertAlmostEqual(j['save_effort'], 5.0 * (1 - 0.70 / 2.5))

    def test_under_fits_and_effort_only(self):
        self.assertEqual(app.fit_judge(unit(n_files=12, calls=90))['verdict'], 'under')   # architect on opus
        self.assertEqual(app.fit_judge(unit(calls=60, effort='medium'))['verdict'], 'fits')
        j = app.fit_judge(unit(calls=60, effort='xhigh'))
        self.assertEqual((j['verdict'], j['save_model']), ('effort-over', 0.0))
        self.assertAlmostEqual(j['save_effort'], 10.0 * (1 - 1 / 2.5))
        self.assertEqual(app.fit_judge(unit(calls=60, effort='low'))['verdict'], 'effort-under')
        self.assertEqual(app.fit_judge(unit(calls=60, effort='unknown'))['verdict'], 'fits')

    def test_unknown_model_is_never_judged_on_model(self):
        j = app.fit_judge(unit(model='mystery-1', calls=20, effort='medium'))
        self.assertEqual((j['verdict'], j['save_model']), ('fits', 0.0))

    def test_a_missing_alternative_price_saves_nothing(self):
        j = app.fit_judge(unit(calls=20, effort='medium'), reprice=lambda u, tier: None)
        self.assertEqual((j['verdict'], j['save_model']), ('over', 0.0))

    def test_session_level_model_for_main_turns(self):
        small = unit(calls=2, n_tools=1, cost=1.0, effort='medium')     # chat -> sonnet
        hard = unit(calls=60, cost=9.0)                                 # everyday -> opus
        self.assertEqual(app.fit_session_tier([small, hard]), 'opus')
        self.assertEqual(app.fit_judge(small, 'opus')['verdict'], 'session')
        self.assertEqual(app.fit_judge(small, 'opus')['save_model'], 0.0)
        self.assertEqual(app.fit_judge(unit(calls=2, n_tools=1), 'opus')['verdict'], 'effort-over')
        j = app.fit_judge(unit(calls=2, n_tools=1, cost=20.0, model='claude-fable-5-2'), 'opus')
        self.assertEqual(j['verdict'], 'over')
        self.assertAlmostEqual(j['save_model'], 10.0)
        self.assertEqual(app.fit_session_tier([small, small]), 'sonnet')
        self.assertIsNone(app.fit_session_tier([]))

    def test_repricing_goes_through_the_collector_price_rules(self):
        catalog = app.default_prices()
        base = dict(id='cl:x', session='Claude:x', provider='Claude', model='claude-opus-5-5', ts=1793527200.0,
                    tier='standard', speed='fast', geo='global', web_searches=0)
        def row(**usage):
            r = dict(base, **app.normalize_usage(dict({'input_tokens': 0, 'output_tokens': 0}, **usage), 'Claude'))
            r.update(app.price_request(r, catalog))
            return r
        opus = row(input_tokens=1_000_000)
        self.assertAlmostEqual(opus['cost'], 8.0)                        # fast mode on Opus 5.5
        self.assertAlmostEqual(app.fit_reprice([opus], 'claude-opus-5-5', catalog), 4.0)    # alternatives at standard
        self.assertAlmostEqual(app.fit_reprice([opus], 'claude-sonnet-5-5', catalog), 2.0)
        write = row(cache_creation_input_tokens=1_000_000, cache_creation={'ephemeral_1h_input_tokens': 1_000_000})
        self.assertAlmostEqual(app.fit_reprice([write], 'claude-fable-5-2', catalog), 16.0)
        short = row(input_tokens=100_000)
        long = row(input_tokens=100_001)
        self.assertAlmostEqual(app.fit_reprice([short], 'claude-haiku-5-5', catalog), 0.01)
        self.assertAlmostEqual(app.fit_reprice([long], 'claude-haiku-5-5', catalog), 0.0500005)
        unpriced = dict(opus, cost=None)
        self.assertAlmostEqual(app.fit_reprice([opus, unpriced], 'claude-sonnet-5-5', catalog), 2.0)
        thin = dict(catalog, models={k: v for k, v in catalog['models'].items() if k != 'claude-haiku-5-5'})
        self.assertIsNone(app.fit_reprice([opus], 'claude-haiku-5-5', thin))


class EventTests(FitCase):
    def test_switch_cold_rewrite_effort_change_and_compaction(self):
        big = dict(read=100_000, cw=0)
        self.session([human('q'),
                      assistant('m1', ts='2026-11-01T10:00:00.000Z', **big),
                      assistant('m2', ts='2026-11-01T10:01:00.000Z', model='claude-fable-5-2', read=0, cw=100_000, cw1h=100_000),
                      assistant('m3', ts='2026-11-01T10:02:00.000Z', model='claude-fable-5-2', **big),
                      assistant('m4', ts='2026-11-01T12:02:00.000Z', model='claude-fable-5-2', read=0, cw=100_000, cw1h=100_000),
                      assistant('m5', ts='2026-11-01T15:00:00.000Z', model='claude-fable-5-2', read=0, cw=30_000),  # compacted
                      assistant('m6', ts='2026-11-01T15:00:05.000Z', model='claude-fable-5-2', read=30_000, effort='low')])
        snap = self.snapshot('--all-time')
        ev = snap['fit_analysis']['events']
        self.assertEqual([(e['from'], e['to']) for e in ev['switches']], [('claude-opus-5-5', 'claude-fable-5-2')])
        self.assertAlmostEqual(ev['switches'][0]['cost'], 1.6)
        self.assertEqual([c['gap_min'] for c in ev['cold']], [120])
        self.assertEqual([(e['from'], e['to']) for e in ev['effort_changes']], [('high', 'low')])
        self.assertEqual([(d['date'], d['calls']) for d in ev['daily']], [('2026-11-01', 6)])
        data = self.fit_json('--all-time')
        ids = [i['id'] for i in data['insights']]
        self.assertIn('switches', ids)
        self.assertIn('cold-cache', ids)

    def test_subagent_calls_are_not_main_thread_events(self):
        main = self.session([human('q'), assistant('m1', read=250_000)])
        self.agent(main, 'a1', [human('p'), assistant('s1', model='claude-haiku-5-5', read=150_000,
                                                      ts='2026-11-01T10:00:30.000Z')])
        daily = self.snapshot('--all-time')['fit_analysis']['events']['daily']
        self.assertEqual([(d['calls'], d['big_calls'], d['haiku_long_calls']) for d in daily], [(1, 1, 0)])


class WindowTests(FitCase):
    def test_window_counts_units_by_their_start_date(self):
        self.session([human('old'), assistant('o1', ts='2026-10-01T10:00:00.000Z')], name='old')
        self.session([human('new'), assistant('n1', ts='2026-11-01T10:00:00.000Z'),
                      assistant('n2', ts='2026-11-02T10:00:00.000Z')], name='new')
        data = self.fit_json('--from', '2026-11-01', '--to', '2026-11-30')
        self.assertEqual((data['totals']['units'], data['totals']['sessions']), (1, 1))
        self.assertEqual(data['period'], {'from': '2026-11-01', 'to': '2026-11-30'})
        self.assertEqual(sorted(data['days']), ['2026-11-01', '2026-11-02'])
        everything = self.fit_json('--all-time')
        self.assertEqual(everything['totals']['units'], 2)
        self.assertEqual(everything['period'], {'from': '2026-10-01', 'to': '2026-11-01'})
        self.assertAlmostEqual(everything['totals']['cost'], sum(sum(v.values()) for v in everything['days'].values()), places=3)

    def test_days_end_today(self):
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        stamp = lambda days: (now - dt.timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        self.session([human('recent', ts=stamp(1)), assistant('r1', ts=stamp(1))], name='recent')
        self.session([human('older', ts=stamp(20)), assistant('o1', ts=stamp(20))], name='older')
        self.assertEqual(self.fit_json('--days', '7')['totals']['units'], 1)
        self.assertEqual(self.fit_json('--days', '30')['totals']['units'], 2)

    def test_period_argument_errors(self):
        self.session([human('q'), assistant('m1')])
        for extra, text in ((['--days', '0'], 'positive'), (['--all-time', '--from', '2026-11-01'], 'cannot be combined'),
                            (['--from', '2026-11-05', '--to', '2026-11-01'], 'on or before')):
            with self.assertRaises(ValueError) as caught, contextlib.redirect_stdout(io.StringIO()):
                app.main(self.argv('fit', *extra))
            self.assertIn(text, str(caught.exception))
        result = self.cli('fit', '--from', '11/01/2026')
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.startswith('Error:') and 'Traceback' not in result.stderr, result.stderr[-300:])


class CommandTests(FitCase):
    def test_fit_period_text_and_json_with_examples_largest_first(self):
        self.bundle()
        for i in range(3):     # three small sessions on Opus that the guide would run on Sonnet
            self.session([human(f'question {i}'), assistant(f'q{i}', read=1000 * (i + 1) ** 3, out=500)], name=f'chat{i}')
        text = self.run_main('fit', '--from', '2026-11-01', '--to', '2026-11-01')
        self.assertIn('Model fit, 2026-11-01 to 2026-11-01 (UTC)', text)
        self.assertIn('Findings', text)
        data = self.fit_json('--from', '2026-11-01', '--to', '2026-11-01')
        over = next(i for i in data['insights'] if i['id'] == 'model-over')
        savings = [e['save_model'] for e in over['examples']]
        self.assertEqual(savings, sorted(savings, reverse=True))
        self.assertGreaterEqual(len(over['examples']), 3)
        self.assertEqual({e['kind'] for e in over['examples']} - {'turn', 'agent'}, set())
        for key in ('period', 'totals', 'by_model', 'by_effort', 'days', 'classes', 'insights', 'sessions',
                    'guide', 'note', 'generated', 'price_as_of'):
            self.assertIn(key, data)
        self.assertEqual(json.loads((self.output / 'fit-report.json').read_text())['totals'], data['totals'])
        self.assertNotIn(PROMPT_MARK, json.dumps(data))
        self.assertNotIn('question 0', json.dumps(data))
        titled = self.fit_json('--from', '2026-11-01', '--to', '2026-11-01', '--include-titles')
        whats = [e['what'] for i in titled['insights'] for e in i['examples'] if 'what' in e]
        self.assertTrue(any('question' in w for w in whats), whats)

    def test_fit_session_view_by_id_and_prefix(self):
        self.bundle()
        text = self.run_main('fit', '--session', 's')
        self.assertIn('Session Claude:s1:', text)
        self.assertIn('Turns (main thread)', text)
        self.assertIn('Subagents (grouped)', text)
        self.assertNotIn(PROMPT_MARK, text)
        data = self.fit_json('--session', 'Claude:s1')
        self.assertEqual(data['session'], 'Claude:s1')
        self.assertEqual([(u['kind'], u['n']) for u in data['units']],
                         [('turn', 1), ('agent', None), ('agent', None), ('turn', 2)])
        self.assertTrue(all('title' not in u for u in data['units']))
        titled = self.fit_json('--session', 's1', '--include-titles')
        self.assertIn(PROMPT_MARK, titled['units'][0]['title'])

    def test_fit_session_errors(self):
        self.session([human('q'), assistant('m1')], name='dup-1')
        self.session([human('q'), assistant('m1b')], name='dup-2')
        self.session([human('only a prompt')], name='empty1')
        main = self.session([human('q'), assistant('m9')], name='parent')
        self.agent(main, 'x1', [human('p'), assistant('s9')])
        self.assertIn("matches 2 sessions", self.refusal('fit', '--session', 'dup'))
        self.assertIn('no Claude Code session', self.refusal('fit', '--session', 'nope'))
        self.assertIn('no Claude Code session', self.refusal('fit', '--session', 'du[p'))
        self.assertIn('no recorded model calls', self.refusal('fit', '--session', 'empty1'))
        self.assertIn('subagent run', self.refusal('fit', '--session', 'Claude:parent/agent-x1'))
        self.assertIn('unique prefix', self.refusal('fit', '--session', 'Claude:'))
        self.assertIn('Session Claude:dup-1', self.run_main('fit', '--session', 'dup-1'))

    def test_fit_empty_period(self):
        self.session([human('q'), assistant('m1')])
        self.assertIn('no Claude Code model calls between 2027-01-01 and 2027-01-02',
                      self.refusal('fit', '--from', '2027-01-01', '--to', '2027-01-02'))

    def test_error_paths_exit_non_zero_without_a_traceback(self):
        self.session([human('q'), assistant('m1')], name='dup-1')
        self.session([human('q'), assistant('m1b')], name='dup-2')
        for args in (['fit', '--session', 'dup'], ['fit', '--session', 'nope'], ['fit', '--from', '2030-01-01'],
                     ['suggest', '--session', 'nope'], ['fit', '--days', '0']):
            result = self.cli(*args)
            self.assertEqual(result.returncode, 1, args)
            self.assertTrue(result.stderr.strip() and 'Traceback' not in result.stderr, (args, result.stderr[-300:]))
            self.assertEqual(result.stdout, '')

    def test_suggest_current_model_context_and_switch_cost(self):
        self.session([human(f'please review the parser {PROMPT_MARK}'),
                      assistant('m1', tools=[('Read', {'file_path': '/a'})]), tool_result(),
                      assistant('m2', ts='2026-11-01T10:01:00.000Z', read=250_000)], name='abc123')
        settings = self.home / '.claude/settings.json'
        settings.write_text(json.dumps({'model': 'claude-fable-5-2', 'effortLevel': 'xhigh',
                                        'modelSettings': {'claude-opus-5-5': {'effortLevel': 'high'}, 'bad': 5}}))
        data = json.loads(self.run_main('suggest', '--session', 'abc', '--json'))
        current = data['current']
        self.assertEqual((current['model'], current['effort'], current['context_tokens']), ('claude-opus-5-5', 'high', 250_010))
        self.assertNotIn('opus', current['switch_now_usd'])
        self.assertAlmostEqual(current['switch_now_usd']['fable'], 4.0, places=2)
        self.assertAlmostEqual(current['cache_read_per_call_usd'], 0.05, places=3)
        self.assertEqual(current['settings'], {'model': 'claude-fable-5-2', 'effortLevel': 'xhigh',
                                               'modelSettings': {'claude-opus-5-5': {'effortLevel': 'high'}}})
        self.assertEqual(data['turns'][0]['class'], 'chat')
        self.assertNotIn(PROMPT_MARK, json.dumps(data))
        text = self.run_main('suggest', '--session', 'abc123')
        self.assertIn('Guide (start here', text)
        self.assertIn('Haiku 5.5 $0.10 / $0.50 / $0.01 (5 times that above a 100k prompt)', text)
        self.assertIn('overridden per model: opus-5-5 high', text)
        self.assertIn(PROMPT_MARK, self.run_main('suggest', '--session', 'abc123', '--include-titles'))

    def test_suggest_picks_the_session_from_the_environment_or_the_directory(self):
        work = self.root / 'work' / 'my.proj'
        work.mkdir(parents=True)
        folder = ''.join(c if c.isalnum() and c.isascii() else '-' for c in os.path.realpath(work))
        self.session([human('older'), assistant('o1')], name='older', project=folder)
        self.session([human('newer'), assistant('n1', ts='2026-11-02T10:00:00.000Z')], name='newer', project=folder)
        self.session([human('elsewhere'), assistant('e1', ts='2026-11-03T10:00:00.000Z')], name='elsewhere')
        result = self.cli('suggest', '--json', cwd=work)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['current']['session'], 'Claude:newer')
        result = self.cli('suggest', '--json', '--session', '${CLAUDE_SESSION_ID}', cwd=work)
        self.assertEqual(json.loads(result.stdout)['current']['session'], 'Claude:newer')
        result = self.cli('suggest', '--json', cwd=work, env={'CLAUDE_SESSION_ID': 'elsewhere'})
        self.assertEqual(json.loads(result.stdout)['current']['session'], 'Claude:elsewhere')
        result = self.cli('suggest', cwd=self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn('no Claude Code session found for this directory', result.stderr)

    def test_suggest_without_a_reply_and_with_malformed_settings(self):
        self.session([human('only a prompt')], name='empty1')
        self.session([human('q'), assistant('m1')], name='full1')
        settings = self.home / '.claude/settings.json'
        for raw in ('null', '[]', '{"modelSettings": null}', '{"modelSettings": {"x": 5}, "model": 7}', '{broken',
                    '{"modelSettings": [1, 2], "effortLevel": {"a": 1}}'):
            settings.write_text(raw)
            for name in ('empty1', 'full1'):
                data = json.loads(self.run_main('suggest', '--session', name, '--json'))
                self.assertEqual(data['current']['settings'], {}, raw)
        settings.write_text(json.dumps({'model': 'claude-sonnet-5-5', 'effortLevel': 'medium'}))
        data = json.loads(self.run_main('suggest', '--session', 'empty1', '--json'))
        self.assertEqual((data['current']['model'], data['current']['effort'], data['current']['context_tokens']),
                         ('claude-sonnet-5-5', 'medium', None))
        self.assertEqual(data['turns'], [])
        self.assertIn('no finished turn recorded yet', self.run_main('suggest', '--session', 'empty1'))


class SnapshotContractTests(FitCase):
    def build(self, *extra):
        main = self.bundle()
        self.agent(main, 'c3', [human('read'), assistant('s3', model='claude-sonnet-5-5', ts='2026-11-01T10:06:00.000Z')],
                   meta={'agentType': 'general-purpose', 'model': 'sonnet'})
        big = dict(read=100_000, cw=0)
        self.session([human('q'),
                      assistant('e1', ts='2026-11-01T10:00:00.000Z', **big),
                      assistant('e2', ts='2026-11-01T10:01:00.000Z', model='claude-fable-5-2', read=0, cw=100_000, cw1h=100_000),
                      assistant('e3', ts='2026-11-01T12:02:00.000Z', model='claude-fable-5-2', read=0, cw=100_000, cw1h=100_000),
                      assistant('e4', ts='2026-11-01T12:03:00.000Z', model='claude-fable-5-2', read=100_000, effort='low')],
                     name='events')
        return self.snapshot('--all-time', *extra)

    def assert_contract(self, model_fit, titles):
        self.assertEqual(set(model_fit), CONTRACT_TOP)
        self.assertEqual(model_fit['schema'], 1)
        self.assertTrue(model_fit['note'])
        for item in model_fit['guide']:
            self.assertEqual(set(item), CONTRACT_GUIDE)
        self.assertEqual({u['kind'] for u in model_fit['units']}, {'turn', 'agent'})
        for u in model_fit['units']:
            self.assertEqual(set(u), CONTRACT_UNIT | ({'title'} if titles else set()), u)
            self.assertIsInstance(u['ts'], int)
            self.assertIn(u['verdict'], ('over', 'under', 'effort-over', 'effort-under', 'session', 'fits'))
            self.assertIn(u['class'], app.FIT_CLASSES)
        self.assertEqual(set(model_fit['events']), set(CONTRACT_EVENTS))
        for name, keys in CONTRACT_EVENTS.items():
            self.assertTrue(model_fit['events'][name], name)
            for item in model_fit['events'][name]:
                self.assertEqual(set(item), keys, name)

    def test_every_contract_key_survives_the_json_round_trip(self):
        snap = self.build()
        self.assert_contract(json.loads(json.dumps(snap['model_fit'])), titles=False)
        titled = self.build('--include-titles')
        self.assert_contract(json.loads(json.dumps(titled['model_fit'])), titles=True)
        turn = next(u for u in titled['model_fit']['units'] if u['kind'] == 'turn' and u['session'] == 'Claude:s1')
        self.assertIn(PROMPT_MARK, turn['title'])

    def test_units_use_the_same_session_project_and_date_as_rows(self):
        snap = self.build()
        rows = {(r['session'], r['project'], r['date']) for r in snap['rows']}
        for u in snap['model_fit']['units']:
            self.assertIn((u['session'], u['project'], u['date']), rows)
        claude_cost = sum(r['cost'] for r in snap['rows'] if r['provider'] == 'Claude')
        self.assertAlmostEqual(sum(u['cost'] for u in snap['model_fit']['units']), claude_cost, places=3)

    def test_no_path_and_no_prompt_text_without_titles(self):
        snap = self.build()
        public = json.dumps(snap['model_fit'], ensure_ascii=False)
        for secret in (PROMPT_MARK, PATH_MARK, 'do the thing', str(self.home), 'demo-proj/x', '.jsonl'):
            self.assertNotIn(secret, public)
        self.run_main('dashboard')
        page = (self.output / 'dashboard.html').read_text(encoding='utf-8')
        for secret in (PROMPT_MARK, PATH_MARK, 'do the thing'):
            self.assertNotIn(secret, page)
        self.assertIn('"model_fit"', page)

    def test_open_dashboards_get_model_fit_on_live_updates(self):
        snap = self.build()
        output = self.root / 'shared'
        args = app.parser().parse_args(['chart', '--output', str(output)])
        published = app.publish_shared_usage(dict(snap, sync_revision='1'.zfill(20)), args, '2'.zfill(20))
        self.assertEqual(published['snapshot']['model_fit'], snap['model_fit'])
        shared = json.loads((output / 'usage-state.json').read_text())
        self.assertEqual(shared['snapshot']['model_fit']['units'], snap['model_fit']['units'])
        for secret in (PROMPT_MARK, PATH_MARK):
            self.assertNotIn(secret, (output / 'usage-state.json').read_text())
        budget = app.publish_shared_usage({}, args, budget_only=True)
        self.assertEqual(budget['snapshot']['model_fit'], snap['model_fit'])

    def test_codex_and_cowork_requests_are_not_units(self):
        self.session([human('q'), assistant('m1')])
        cowork = self.home / 'Library/Application Support/Claude/local-agent-mode-sessions/s9/audit.jsonl'
        write_jsonl(cowork, [human('q'), assistant('cw1', ts='2026-11-01T11:00:00.000Z')])
        codex = self.home / '.codex/sessions/rollout.jsonl'
        write_jsonl(codex, [{'type': 'session_meta', 'payload': {'id': 'one', 'cwd': '/work/a'}},
                            {'type': 'turn_context', 'payload': {'model': 'gpt-5.6-sol'}},
                            {'type': 'event_msg', 'timestamp': '2026-11-01T01:00:00Z', 'payload': {
                                'type': 'token_count', 'info': {'last_token_usage': {'input_tokens': 10, 'output_tokens': 1},
                                                                'total_token_usage': {'input_tokens': 10, 'output_tokens': 1,
                                                                                      'total_tokens': 11}}}}])
        snap = self.snapshot('--all-time')
        self.assertEqual(snap['summary']['requests'], 3)
        self.assertEqual([u['session'] for u in snap['model_fit']['units']], ['Claude:s1'])


if __name__ == '__main__':
    unittest.main()
