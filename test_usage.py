"""Text/JSON reporting contracts using synthetic observations only."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent_usage as app


class ReportTests(unittest.TestCase):
    def row(self, date='2026-09-05', **values):
        row = dict(date=date, provider='Codex', model='gpt-6-astra', session='Codex:one',
                   project='example', role='main', requests=1, input=1000, cached=400,
                   write=0, output=100, total=1100, cost=2., cost_high=2., unpriced=0,
                   max_context=1000, parts=[1., 0., 0., 1., 0.], assumed=0, write_unknown=0)
        row.update(values)
        return row

    def report(self, rows, *options):
        snapshot = dict(rows=rows, requests=[dict(row, id=str(i)) for i, row in enumerate(rows)],
                        as_of_date='2026-09-05', generated='2026-09-05T12:00:00+00:00',
                        timezone='UTC', price_as_of='2026-09-05', quality={}, scan={}, summary={})
        return app.usage_report(snapshot, app.parser().parse_args(['usage', *options]))

    def test_default_week_and_exact_summary_format(self):
        rows = [self.row(session='Codex:' + str(i), requests=4596 if i == 0 else 1,
                         input=29_000_123 - 34_000 if i == 0 else 1000,
                         output=1_279_999 - 3400 if i == 0 else 100,
                         total=30_280_122 - 37_400 if i == 0 else 1100,
                         cost=1327.32 if i == 0 else 0., cost_high=1327.32 if i == 0 else 0.) for i in range(35)]
        result = self.report(rows + [self.row('2026-08-29')])
        self.assertEqual(result['period'], {'from': '2026-08-30', 'to': '2026-09-05', 'days': 7})
        self.assertEqual(result['previous_period']['from'], '2026-08-23')
        self.assertEqual(app.usage_text(result).splitlines()[0],
                         'For Aug 30–Sep 5: $1,327.32 estimated API cost. In: 29M, Out: 1.28M')
        totals = result['current']['totals']
        self.assertEqual((totals['requests'], totals['sessions']), (4630, 35))
        self.assertEqual((totals['input_tokens'], totals['output_tokens']), (29_000_123, 1_279_999))
        self.assertEqual(result['previous']['totals']['requests'], 1)

    def test_filters_apply_to_both_periods_and_request_details(self):
        rows = [self.row(date, provider=provider, model='claude-opus-5', project=project, role=role)
                for date in ['2026-09-05', '2026-08-29', '2026-08-22']
                for provider in ['Claude', 'Codex'] for project in ['example', 'other']
                for role in ['main', 'subagent']]
        report = self.report(rows, '--provider', 'Anthropic', '--model', 'claude-opus-5',
                             '--project', 'example', '--role', 'subagent', '--include-requests')
        for period in [report['current'], report['previous']]:
            self.assertEqual(period['totals']['requests'], 1)
            self.assertEqual(len(period['requests']), 1)
            self.assertEqual(period['requests'][0]['provider'], 'Claude')
        self.assertEqual(report['changes']['requests']['percent'], 0)

    def test_distinct_sessions_and_weighted_cache(self):
        rows = [self.row(input=100, cached=100), self.row('2026-09-04', model='gpt-5.6-sol', input=900, cached=0)]
        report = self.report(rows)
        self.assertEqual(report['current']['totals']['sessions'], 1)
        self.assertAlmostEqual(report['current']['totals']['cache_share'], .1)
        self.assertEqual(len(report['current']['by_model']), 2)
        self.assertEqual(len(report['current']['by_session']), 1)
        self.assertEqual([value['name'] for value in report['current']['by_date']], ['2026-09-04', '2026-09-05'])

    def test_missing_records_do_not_mean_zero_usage(self):
        report = self.report([self.row('2026-08-29')])
        self.assertEqual(report['changes']['status'], 'no_current_data')
        self.assertIsNone(report['current']['totals']['estimated_cost_usd'])
        self.assertEqual(self.report([self.row()])['changes']['status'], 'no_previous_data')
        self.assertEqual(self.report([self.row('2020-01-01')])['period']['to'], '2026-09-05')

    def test_unknown_prices_and_ranges_suppress_cost_comparisons(self):
        unknown = self.row(model='future-model', cost=0., cost_high=0., unpriced=1)
        report = self.report([unknown, self.row('2026-08-29')])
        self.assertIsNone(report['current']['totals']['estimated_cost_usd'])
        self.assertEqual(report['unknown_models'], ['future-model'])
        self.assertEqual(report['changes']['estimated_cost_usd']['status'], 'incomplete_pricing')
        report = self.report([unknown, self.row(), self.row('2026-08-29')])
        self.assertEqual(report['current']['totals']['estimated_cost_usd'], 2.)
        self.assertIn('partial; 1 unpriced requests', app.usage_text(report))
        report = self.report([self.row(cost_high=3.), self.row('2026-08-29')])
        self.assertIn('$2.00–$3.00', app.usage_text(report))
        self.assertEqual(report['changes']['estimated_cost_usd']['status'], 'incomplete_pricing')

    def test_zero_baseline_and_cache_percentage_points(self):
        report = self.report([self.row(cached=500), self.row('2026-08-29', cost=0., cost_high=0., cached=100)])
        self.assertEqual(report['changes']['estimated_cost_usd']['status'], 'zero_baseline')
        self.assertIsNone(report['changes']['estimated_cost_usd']['percent'])
        self.assertAlmostEqual(report['changes']['cache_share']['percentage_points'], 40.)

    def test_calendar_ranges_and_all_time(self):
        report = self.report([], '--from', '2024-02-28', '--to', '2024-03-01')
        self.assertEqual(report['period']['days'], 3)
        self.assertEqual(report['previous_period']['from'], '2024-02-25')
        report = self.report([], '--to', '2026-01-03')
        self.assertIn('2025-12-28–2026-01-03', app.usage_text(report))
        report = self.report([self.row('2020-01-01'), self.row()], '--all-time')
        self.assertEqual(report['period']['from'], '2020-01-01')
        self.assertIsNone(report['previous'])
        self.assertEqual(report['changes']['status'], 'not_requested')
        for options in [('--days', '0'), ('--from', 'bad-date'), ('--from', '2026-09-10'),
                        ('--all-time', '--to', '2026-09-05'), ('--provider', 'unsupported')]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.report([], *options)

    def test_usage_cli_json_is_pure_and_does_not_generate_html_or_network(self):
        with tempfile.TemporaryDirectory(prefix='usage report ') as temporary:
            root = Path(temporary)
            trace = root / 'profile/.claude/projects/example/one.jsonl'
            trace.parent.mkdir(parents=True)
            trace.write_text(json.dumps(dict(type='assistant', timestamp='2026-09-01T00:00:00Z',
                message=dict(id='synthetic', model='claude-opus-5',
                             content=[dict(type='text', text='PRIVATE TRANSCRIPT SHOULD NOT APPEAR')],
                             usage=dict(input_tokens=100, output_tokens=10)))) + '\n', encoding='utf-8')
            output = root / 'report'
            arguments = ['usage', '--json', '--include-requests', '--home', str(root / 'profile'),
                         '--output', str(output), '--timezone', 'UTC', '--to', '2026-09-05']
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout), patch('socket.socket', side_effect=AssertionError('Network used')):
                app.main(arguments)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report['current']['totals']['requests'], 1)
            self.assertEqual(len(report['current']['requests']), 1)
            self.assertNotIn('PRIVATE TRANSCRIPT', stdout.getvalue())
            self.assertEqual(json.loads((output / 'usage-report.json').read_text(encoding='utf-8')), report)
            self.assertFalse((output / 'dashboard.html').exists())
            self.assertFalse((output / 'status.json').exists())
            (output / 'dashboard.html').write_text('Existing dashboard', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                app.main(arguments)
            self.assertEqual((output / 'dashboard.html').read_text(encoding='utf-8'), 'Existing dashboard')


if __name__ == '__main__':
    unittest.main()
