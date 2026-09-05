"""Diagnostics, counterfactual arithmetic, local privacy and status-line contracts."""
import collections
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent_usage as app


class AnalysisTests(unittest.TestCase):
    def row(self, index=0, incoming=20000, cached=15000, **changes):
        row = dict(id='cx:' + str(index), session='Codex:one', provider='Codex',
                   model='gpt-6-astra', date='2026-09-05', ts=1788600000 + index * 60,
                   project='test', role='main', tier='standard', speed='standard', geo='global',
                   trace_stats={}, trace_observed=True, effort='high', web_searches=None)
        row.update(app.normalize_usage(dict(input_tokens=incoming, cached_input_tokens=cached,
                                            output_tokens=100), 'Codex'))
        row.update(changes)
        row.update(app.price_request(row, app.default_prices()))
        return row

    def analyze(self, rows, managed=()):
        records = app.analyze_requests(rows, app.default_prices(), managed)['records']
        return records, app.diagnostics_summary(records)

    def test_overlapping_scenarios_use_largest_per_request(self):
        rows = [self.row(0, tier='priority'), self.row(1, tier='priority')]
        records, summary = self.analyze(rows)
        self.assertEqual({f['rule'] for f in summary['findings']}, {'model_routing', 'premium_mode'})
        for record in records:
            self.assertAlmostEqual(record['scenario_usd'], max(s['savings_usd'] for s in record['checks']))
        # 20K input, 15K cached, 100 output: $0.07 Standard, $0.14 Priority.
        # Same usage on Sol Priority is $0.056; routing delta is $0.084/request.
        self.assertAlmostEqual(summary['scenario_savings_usd'], .168)
        self.assertAlmostEqual(summary['affected_cost_usd'], .28)
        self.assertGreater(sum(f['savings_usd'] for f in summary['findings']), summary['scenario_savings_usd'])
        self.assertIn('does not establish task difficulty', app.CHECKS['model_routing']['description'])

    def test_routing_threshold_and_unknown_alternative_are_not_guesses(self):
        for rows in ([self.row()], [self.row(i) for i in range(7)],
                     [self.row(i, incoming=33000) for i in range(2)],
                     [self.row(i, output=5000) for i in range(2)]):
            _, summary = self.analyze(rows)
            self.assertNotIn('model_routing', [f['rule'] for f in summary['findings']])
        cat = app.default_prices()
        del cat['models']['gpt-5.6-sol']
        records = app.analyze_requests([self.row(i) for i in range(2)], cat)['records']
        self.assertTrue(all(not r['checks'] for r in records))

    def test_context_payload_polling_and_premium_are_distinct_drivers(self):
        rows = [self.row(0, incoming=100000), *[self.row(i, incoming=300000) for i in range(1, 4)]]
        rows[-1]['trace_stats'] = dict(max_tool_bytes=45000, max_mcp_bytes=45000, poll_calls=5)
        _, summary = self.analyze(rows)
        findings = {f['rule']: f for f in summary['findings']}
        self.assertEqual(set(findings), {'initial_context', 'context_growth', 'large_tool_result', 'long_context', 'polling'})
        self.assertEqual(findings['context_growth']['requests'], 1)
        self.assertAlmostEqual(findings['long_context']['premium_usd'], 3 * (285000 * 10 + 15000 * 1 + 100 * 25) / 1e6)
        self.assertIsNone(summary['scenario_savings_usd'])
        self.assertTrue(all(f['savings_usd'] is None for f in findings.values()))

    def test_cache_rebuild_caps_counterfactual_to_previous_prefix(self):
        rows = [self.row(0, incoming=100000, cached=90000),
                self.row(1, incoming=200000, cached=0, ts=1788600600)]
        records, summary = self.analyze(rows)
        finding = next(f for f in summary['findings'] if f['rule'] == 'cache_rebuild')
        self.assertEqual(finding['evidence']['possible_prefix_tokens'], 100000)
        self.assertAlmostEqual(finding['savings_usd'], .9)
        self.assertEqual(records[1]['gap_seconds'], 600)
        for changes in ({'ts': 1788600299}, {'model': 'gpt-5.6-sol'}, {'cached': 100000}):
            alternative = self.row(1, incoming=200000, **changes)
            _, summary = self.analyze([rows[0], alternative])
            self.assertNotIn('cache_rebuild', [f['rule'] for f in summary['findings']])

    def test_unknown_ttl_does_not_create_false_long_context_or_mode_savings(self):
        row = self.row(provider='Claude', model='claude-sonnet-4-6', session='Claude:one')
        row.update(app.normalize_usage(dict(input_tokens=100, cache_read_input_tokens=1000,
                                            cache_creation_input_tokens=20000, output_tokens=50), 'Claude'))
        row.update(app.price_request(row, app.default_prices()))
        self.assertGreater(row['cost_high'], row['cost'])
        _, summary = self.analyze([row])
        self.assertEqual(summary['finding_count'], 0)
        self.assertIsNone(app.scenario_delta(row, row))
        candidate = app.cache_scenario(row, 12000)
        self.assertEqual(candidate['input'], row['input'])
        self.assertEqual(candidate['uncached'] + candidate['cached'] + candidate['write'], row['input'])
        self.assertEqual(candidate['write_unknown'], 8100)

    def test_unpriced_findings_keep_nulls(self):
        _, summary = self.analyze([self.row(incoming=120000, model='unknown-model')])
        self.assertEqual(summary['finding_count'], 1)
        self.assertIsNone(summary['affected_cost_usd'])
        self.assertIsNone(summary['findings'][0]['observed_cost_usd'])
        self.assertIsNone(summary['scenario_savings_usd'])
        self.assertEqual(summary['unpriced_flagged_requests'], 1)

    def test_managed_children_inherit_but_subagents_are_not_implicitly_managed(self):
        rows = [self.row(), self.row(1, session='Codex:child', role='subagent', parent_session='Codex:one'),
                self.row(2, session='Codex:other', role='subagent')]
        records, _ = self.analyze(rows, ['Codex:one'])
        self.assertEqual({r['session']: r['pool'] for r in records},
                         {'Codex:one': 'managed', 'Codex:child': 'managed', 'Codex:other': 'interactive'})

    def test_budget_thresholds_and_partial_prices(self):
        empty = app.budget_status([], 100)
        self.assertEqual(empty['status'], 'no_data')
        self.assertIsNone(empty['used_percent'])
        for value, level in [(49.99, 0), (50, 50), (80, 80), (100, 100), (130, 100)]:
            status = app.budget_status([dict(cost=value, cost_high=value)], 100)
            self.assertEqual(status['nudge_percent'], level)
        status = app.budget_status([dict(cost=80, cost_high=85), dict(cost=None, cost_high=None)], 100)
        self.assertEqual(status['status'], 'partial_pricing')
        self.assertFalse(status['pricing_complete'])
        for invalid in [0, -1, float('inf'), float('nan')]:
            with self.assertRaises(ValueError): app.budget_status([], invalid)

    def test_text_analysis_preserves_cost_ranges_and_tariff_premiums(self):
        _, summary = self.analyze([self.row(incoming=300000)])
        finding = summary['findings'][0]
        finding.update(observed_cost_usd=1., cost_high_usd=2., premium_usd=.5, premium_high_usd=.8)
        with patch.object(app, 'usage_text', return_value='Weekly usage'):
            text = app.analysis_text({'current': {'diagnostics': summary}})
        self.assertIn('associated cost $1.00–$2.00', text)
        self.assertIn('tariff premium $0.50–$0.80', text)

    def test_codex_tool_payload_privacy_and_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'one.jsonl'
            payload = 'PRIVATE_PAYLOAD_' * 3000
            events = [dict(type='session_meta', payload=dict(id='one', cwd='/demo/project')),
                      dict(type='turn_context', payload=dict(model='gpt-6-astra'))]
            call = dict(type='response_item', payload=dict(type='function_call', call_id='call', name='mcp__tool__wait', arguments='PRIVATE_ARGUMENT'))
            result = dict(type='response_item', payload=dict(type='function_call_output', call_id='call', output=payload))
            events += [call, call, result, result, dict(type='event_msg', timestamp='2026-09-05T00:00:00Z', payload=dict(type='token_count', info=dict(last_token_usage=dict(input_tokens=100, output_tokens=2))))]
            path.write_text('\n'.join(json.dumps(e) for e in events), encoding='utf-8')
            parsed = app.parse_codex(path)
            stats = parsed['requests'][0]['trace_stats']
            self.assertEqual((stats['tool_calls'], stats['tool_results'], stats['poll_calls']), (1, 1, 1))
            self.assertEqual(stats['mcp_bytes'], len(payload.encode()))
            self.assertNotIn('PRIVATE', json.dumps(parsed))
            merged = app.merge_requests(parsed['requests'] * 2, collections.Counter())
            self.assertEqual(merged[0]['trace_stats']['tool_bytes'], stats['tool_bytes'])

    def test_claude_stdin_statusline_and_analysis_work_offline_without_dashboard(self):
        with tempfile.TemporaryDirectory(prefix='analysis profile ') as directory:
            root = Path(directory);trace = root / 'home/.claude/projects/demo/one.jsonl';trace.parent.mkdir(parents=True)
            messages = [dict(type='assistant', timestamp='2026-09-05T00:00:00Z', message=dict(id='one', model='claude-opus-5', usage=dict(input_tokens=100, output_tokens=10), content=[dict(type='tool_use', id='call', name='mcp__test', input={'text': 'PRIVATE'})])),
                        dict(type='user', timestamp='2026-09-05T00:00:30Z', message=dict(content=[dict(type='tool_result', tool_use_id='call', content='SECRET' * 8000)])),
                        dict(type='assistant', timestamp='2026-09-05T00:01:00Z', message=dict(id='two', model='claude-opus-5', usage=dict(input_tokens=100, output_tokens=10), content=[]))]
            trace.write_text('\n'.join(json.dumps(x) for x in messages), encoding='utf-8')
            common = ['--json', '--home', str(root / 'home'), '--output', str(root / 'report'), '--to', '2026-09-05', '--timezone', 'UTC']
            for command in ['analyze', 'statusline']:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout), patch('socket.socket', side_effect=AssertionError('Network used')), patch('sys.stdin', io.StringIO('{"session_id":"one"}')):
                    app.main([command, *common, *(['--stdin', '--provider', 'Codex'] if command == 'statusline' else ['--include-requests'])])
                result = json.loads(stdout.getvalue())
                self.assertNotIn('SECRET', stdout.getvalue());self.assertNotIn('PRIVATE', stdout.getvalue())
                if command == 'analyze':
                    self.assertEqual(result['current']['diagnostics']['tool_stats']['mcp_bytes'], 48000)
                    self.assertEqual(len(result['current']['analysis_records']), 2)
                else:
                    self.assertEqual(result['session']['id'], 'Claude:one')
                    self.assertEqual(result['session']['records'], 2)
                    # A provider filter must not reduce the shared pool.
                    self.assertGreater(result['pools']['interactive']['known_cost_usd'], 0)
                    self.assertIn('Session $', app.statusline_text(result))
            self.assertFalse((root / 'report/dashboard.html').exists())
            self.assertFalse((root / 'report/status.json').exists())
            for path in (root / 'report').glob('*.json'):
                self.assertNotIn('SECRET', path.read_text())

    def test_statusline_watch_retries_source_errors_without_a_server(self):
        with tempfile.TemporaryDirectory() as directory:
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, {'CODEX_THREAD_ID': ''}), patch('socket.socket', side_effect=AssertionError('Network used')), \
                 patch.object(app, 'source_fingerprint', side_effect=['initial', OSError('temporary source error')]), \
                 patch.object(app.time, 'sleep', side_effect=[None, KeyboardInterrupt]), \
                 contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                app.main(['statusline', '--watch', '5', '--home', directory, '--output', directory])
            self.assertIn('Status refresh failed', stderr.getvalue())
            self.assertIn('unavailable', stdout.getvalue())
            self.assertNotIn('\x1b', stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
