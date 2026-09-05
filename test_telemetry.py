"""Measured request statistics, local privacy and status-line contracts."""
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


class TelemetryTests(unittest.TestCase):
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

    def statistics(self, rows, managed=()):
        records = app.request_statistics(rows, managed)
        return records, app.telemetry_summary(records)

    def test_request_statistics_preserve_order_gaps_and_pricing(self):
        rows = [self.row(2, incoming=300000, model='unknown-model'),
                self.row(0, incoming=100000, tier='priority'), self.row(1, incoming=200000)]
        records, summary = self.statistics(rows)
        self.assertEqual([r['step'] for r in records], [1, 2, 3])
        self.assertEqual([r['gap_seconds'] for r in records], [None, 60, 60])
        self.assertEqual([r['input'] for r in records], [100000, 200000, 300000])
        self.assertAlmostEqual(records[0]['cost'], rows[1]['cost'])
        self.assertEqual(records[0]['parts'], rows[1]['cost_parts'])
        self.assertIsNone(records[-1]['cost'])
        self.assertIsNone(records[-1]['cost_high'])
        self.assertEqual(summary['total_records'], 3)

    def test_telemetry_aggregates_counts_but_preserves_maxima_and_coverage(self):
        rows = [self.row(0, trace_stats=dict(tool_calls=5, tool_bytes=50000, max_tool_bytes=45000)),
                self.row(1, trace_stats=dict(tool_calls=2, tool_bytes=12000, max_tool_bytes=12000)),
                self.row(2, trace_observed=False)]
        records, summary = self.statistics(rows)
        self.assertEqual(summary['tool_stats'], dict(tool_calls=7, tool_bytes=62000, max_tool_bytes=45000))
        self.assertEqual((summary['trace_records'], summary['total_records']), (2, 3))
        self.assertEqual(app.telemetry_summary(records[:1])['tool_stats']['tool_calls'], 5)
        self.assertEqual(app.telemetry_summary([]), dict(trace_records=0, total_records=0, tool_stats={}))

    def test_managed_children_inherit_but_subagents_are_not_implicitly_managed(self):
        rows = [self.row(), self.row(1, session='Codex:child', role='subagent', parent_session='Codex:one'),
                self.row(2, session='Codex:other', role='subagent')]
        records, _ = self.statistics(rows, ['Codex:one'])
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

    def test_usage_alias_and_statusline_export_only_statistics_offline(self):
        with tempfile.TemporaryDirectory(prefix='statistics profile ') as directory:
            root = Path(directory);trace = root / 'home/.claude/projects/demo/one.jsonl';trace.parent.mkdir(parents=True)
            messages = [dict(type='assistant', timestamp='2026-09-05T00:00:00Z', message=dict(id='one', model='claude-opus-5', usage=dict(input_tokens=100, output_tokens=10), content=[dict(type='tool_use', id='call', name='mcp__test', input={'text': 'PRIVATE'})])),
                        dict(type='user', timestamp='2026-09-05T00:00:30Z', message=dict(content=[dict(type='tool_result', tool_use_id='call', content='SECRET' * 8000)])),
                        dict(type='assistant', timestamp='2026-09-05T00:01:00Z', message=dict(id='two', model='claude-opus-5', usage=dict(input_tokens=100, output_tokens=10), content=[]))]
            trace.write_text('\n'.join(json.dumps(x) for x in messages), encoding='utf-8')
            common = ['--json', '--home', str(root / 'home'), '--output', str(root / 'report'), '--to', '2026-09-05', '--timezone', 'UTC']
            reports = {}
            for command in ['usage', 'analyze', 'statusline']:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout), patch('socket.socket', side_effect=AssertionError('Network used')), patch('sys.stdin', io.StringIO('{"session_id":"one"}')):
                    app.main([command, *common, *(['--stdin', '--provider', 'Codex'] if command == 'statusline' else ['--include-requests'])])
                result = json.loads(stdout.getvalue())
                self.assertNotIn('SECRET', stdout.getvalue());self.assertNotIn('PRIVATE', stdout.getvalue())
                self.assertEqual(result['schema_version'], 2)
                reports[command] = result
                if command != 'statusline':
                    self.assertEqual(result['current']['telemetry']['tool_stats']['mcp_bytes'], 48000)
                    self.assertEqual(len(result['current']['request_stats']), 2)
                else:
                    self.assertEqual(result['session']['id'], 'Claude:one')
                    self.assertEqual(result['session']['records'], 2)
                    # A provider filter must not reduce the shared pool.
                    self.assertGreater(result['pools']['interactive']['known_cost_usd'], 0)
                    self.assertIn('Session $', app.statusline_text(result))
            self.assertEqual(reports['usage']['current'], reports['analyze']['current'])
            self.assertFalse((root / 'report/dashboard.html').exists())
            self.assertFalse((root / 'report/status.json').exists())
            for path in (root / 'report').glob('*.json'):
                self.assertNotIn('SECRET', path.read_text())
                def assert_statistics(value):
                    if isinstance(value, dict):
                        self.assertFalse(set(value) & {'analysis', 'analysis_rules', 'analysis_records',
                            'diagnostics', 'checks', 'findings', 'scenario_usd', 'scenario_savings_usd',
                            'savings_usd', 'coaching', 'coaching_detail', 'action'})
                        for child in value.values(): assert_statistics(child)
                    elif isinstance(value, list):
                        for child in value: assert_statistics(child)
                assert_statistics(json.loads(path.read_text()))

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
