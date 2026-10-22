"""Menu bar calendar periods, budget reuse and incomplete pricing."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agent_usage as app


class MenuBarTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name)
        self.args = app.parser().parse_args(['menubar', '--output', str(self.output), '--timezone', 'UTC'])

    def report(self, daily=(), today='2026-10-22'):
        records = [dict(date=date, cost=cost, cost_high=cost) for date, cost in daily]
        return app.menubar_report(dict(as_of_date=today, generated=today+'T12:00:00+00:00',
                                       timezone='UTC', request_stats=records), self.args)

    def test_calendar_day_week_month_not_rolling_windows(self):
        result = self.report([('2026-09-30',100), ('2026-10-01',20), ('2026-10-18',30),
                              ('2026-10-19',40), ('2026-10-22',50), ('2026-10-23',1000)])
        self.assertEqual([p['known_cost_usd'] for p in result['periods']], [50,90,140])
        self.assertEqual([p['period']['from'] for p in result['periods']],
                         ['2026-10-22','2026-10-19','2026-10-01'])
        self.assertEqual([p['resets_at'] for p in result['periods']],
                         ['2026-10-23T00:00:00+00:00','2026-10-26T00:00:00+00:00',
                          '2026-11-01T00:00:00+00:00'])
        self.assertIsNone(result['periods'][0]['budget_usd'])
        self.assertIsNone(result['periods'][1]['budget_usd'])

    def test_week_crosses_month_and_year_monday_reset(self):
        result = self.report([('2026-12-27',100),('2026-12-28',10),('2027-01-01',20)], '2027-01-01')
        self.assertEqual([p['known_cost_usd'] for p in result['periods']], [20,30,20])
        self.assertEqual(result['periods'][1]['resets_at'], '2027-01-04T00:00:00+00:00')
        monday = self.report([('2027-01-03',100),('2027-01-04',2)], '2027-01-04')
        self.assertEqual(monday['periods'][1]['known_cost_usd'], 2)

    def test_saved_monthly_budget_shared_with_cli_and_filters_ignored(self):
        (self.output/'budget.json').write_text(json.dumps(
            dict(monthly_budget_usd=100, forecast_enabled=True, custom_field='preserved')))
        self.args.provider = 'absent'
        result = self.report([('2026-10-22',125)])
        self.assertEqual(result['periods'][2]['budget_usd'], 100)
        self.assertEqual(result['periods'][2]['used_percent'], 125)
        self.assertEqual(result['periods'][2]['status'], 'over_budget')
        with contextlib.redirect_stdout(io.StringIO()):
            app.main(['budget','--set','200','--output',str(self.output),'--json'])
        self.assertEqual(self.report()['periods'][2]['budget_usd'], 200)
        self.assertEqual(json.loads((self.output/'budget.json').read_text())['custom_field'], 'preserved')

    def test_no_observations_unpriced_partial_and_observed_zero(self):
        absent = self.report()['periods'][0]
        zero = self.report([('2026-10-22',0)])['periods'][0]
        unknown = self.report([('2026-10-22',None)])['periods'][2]
        partial = self.report([('2026-10-22',None),('2026-10-22',20)])['periods'][2]
        self.assertEqual(absent['observed_requests'], 0)
        self.assertEqual(zero['observed_requests'], 1)
        self.assertEqual(zero['known_cost_usd'], 0)
        self.assertIsNone(unknown['used_percent'])
        self.assertEqual(partial['known_cost_usd'], 20)
        self.assertEqual(partial['unpriced_requests'], 1)
        self.assertEqual(partial['used_percent'], 1)

    def test_cost_range_is_preserved(self):
        snap = dict(as_of_date='2026-10-22',generated='2026-10-22T12:00:00Z',
                    timezone='UTC',request_stats=[dict(date='2026-10-22',cost=2,cost_high=3)])
        period = app.menubar_report(snap,self.args)['periods'][2]
        self.assertEqual((period['known_cost_usd'],period['cost_high_usd']), (2,3))
        self.assertFalse(period['pricing_complete'])

    def test_reset_uses_timezone_dst_and_leap_month(self):
        self.args.timezone = 'America/New_York'
        result = self.report(today='2026-03-07')
        self.assertEqual(result['periods'][0]['resets_at'], '2026-03-08T00:00:00-05:00')
        self.assertEqual(result['periods'][1]['resets_at'], '2026-03-09T00:00:00-04:00')
        self.args.timezone = 'UTC'
        self.assertEqual(self.report(today='2028-02-29')['periods'][2]['resets_at'],
                         '2028-03-01T00:00:00+00:00')

    def test_command_emits_only_aggregate_json_and_does_not_publish_evidence(self):
        snap = dict(as_of_date='2026-10-22',generated='2026-10-22T12:00:00Z',
                    timezone='UTC',request_stats=[dict(date='2026-10-22',cost=10,cost_high=10,
                                                        session='private-id',project='private-name')])
        output = io.StringIO()
        with patch.object(app,'make_snapshot',return_value=snap), contextlib.redirect_stdout(output):
            app.main(['menubar','--json','--output',str(self.output)])
        report = json.loads(output.getvalue())
        self.assertEqual(report['periods'][2]['known_cost_usd'], 10)
        self.assertNotIn('private-', output.getvalue())
        self.assertFalse(app.evidence_wanted(self.args))
        self.assertTrue((self.output/'menubar.json').is_file())
        self.assertFalse((self.output/'sessions.sqlite').exists())


    def test_dashboard_exports_identical_calendar_report_in_json_and_html(self):
        import base64
        import gzip
        home = self.output/'home'
        traces = home/'.claude/projects/example'
        traces.mkdir(parents=True)
        observation = dict(type='assistant', sessionId='dashboard-shared',
            timestamp=app.dt.datetime.now(app.dt.timezone.utc).isoformat(),
            message=dict(id='one', model='claude-sonnet-5.5',
                         usage=dict(input_tokens=1000000, output_tokens=100000)))
        (traces/'one.jsonl').write_text(json.dumps(observation)+'\n')
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            app.main(['dashboard','--json','--home',str(home),'--timezone','UTC',
                      '--output',str(self.output)])
        report = json.loads(stdout.getvalue())
        usage = json.loads((self.output/'usage.json').read_text())
        raw = (self.output/'dashboard.html').read_text().split(
            '<script id="snapshot" type="application/json">')[1].split('</script>')[0]
        public = json.loads(raw)
        if public.get('encoding') == 'gzip-base64':
            public = json.loads(gzip.decompress(base64.b64decode(public['data'])))
        self.assertEqual(report, usage['spend_summary'])
        self.assertEqual(report, public['spend_summary'])
        self.assertEqual(report['generated'], usage['generated'])
        self.assertEqual([p['known_cost_usd'] for p in report['periods']], [3,3,3])
        self.assertEqual(report['periods'][2]['budget_usd'], 2000)
        self.assertNotIn('dashboard-shared', stdout.getvalue())


class MenuBarComparisonTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.args = app.parser().parse_args(['menubar','--output',temporary.name,'--timezone','UTC'])

    def report(self, observations=(), now='2026-10-22T12:00:00+00:00'):
        import datetime as dt
        tz = app.report_timezone(self.args.timezone)
        records = []
        for stamp,cost,*high in observations:
            moment = dt.datetime.fromisoformat(stamp)
            records.append(dict(date=moment.astimezone(tz).date().isoformat(),ts=moment.timestamp(),
                                cost=cost,cost_high=high[0] if high else cost))
        return app.menubar_report(dict(generated=now,timezone=self.args.timezone,
            as_of_date=dt.datetime.fromisoformat(now).astimezone(tz).date().isoformat(),
            request_stats=records),self.args)

    def test_day_uses_yesterday_at_same_time_not_whole_day(self):
        day = self.report([('2026-10-22T10:00:00+00:00',30),
                           ('2026-10-21T10:00:00+00:00',50),
                           ('2026-10-21T18:00:00+00:00',900)])['periods'][0]['comparison']
        self.assertEqual((day['current']['known_cost_usd'],day['previous']['known_cost_usd']),(30,50))
        self.assertEqual((day['absolute_usd'],day['percent']),(-20,-40))
        self.assertEqual(day['previous_period']['to'],'2026-10-21T12:00:00+00:00')

    def test_week_uses_same_weekdays_and_time(self):
        week = self.report([('2026-10-19T10:00:00+00:00',40),('2026-10-22T10:00:00+00:00',10),
                            ('2026-10-12T10:00:00+00:00',20),('2026-10-15T10:00:00+00:00',5),
                            ('2026-10-15T18:00:00+00:00',1000),('2026-10-18T10:00:00+00:00',1000)
                           ])['periods'][1]['comparison']
        self.assertEqual((week['absolute_usd'],week['percent']),(25,100))
        self.assertEqual(week['previous_period']['from'],'2026-10-12T00:00:00+00:00')
        self.assertEqual(week['previous_period']['to'],'2026-10-15T12:00:00+00:00')

    def test_month_uses_same_dates_and_time(self):
        month = self.report([('2026-10-01T10:00:00+00:00',20),('2026-10-22T10:00:00+00:00',10),
                             ('2026-09-01T10:00:00+00:00',30),('2026-09-22T11:00:00+00:00',30),
                             ('2026-09-22T18:00:00+00:00',1000)])['periods'][2]['comparison']
        self.assertEqual((month['absolute_usd'],month['percent']),(-30,-50))
        self.assertEqual(month['previous_period']['to'],'2026-09-22T12:00:00+00:00')

    def test_short_previous_month_matches_complete_days_in_both_months(self):
        report = self.report([('2027-03-01T10:00:00+00:00',5),('2027-03-28T23:00:00+00:00',20),
                              ('2027-03-29T10:00:00+00:00',1000),('2027-03-31T10:00:00+00:00',1000),
                              ('2027-02-01T10:00:00+00:00',10),('2027-02-28T23:00:00+00:00',5)],
                             now='2027-03-31T12:00:00+00:00')
        month = report['periods'][2]
        self.assertEqual(month['known_cost_usd'],2025)
        comparison = month['comparison']
        self.assertEqual(comparison['absolute_usd'],10)
        self.assertEqual(comparison['label'],'vs last month (first 28 days)')
        self.assertEqual(comparison['current_period']['to'],'2027-03-28T23:59:59.999999+00:00')
        leap = self.report(now='2028-03-31T12:00:00+00:00')['periods'][2]['comparison']
        self.assertIn('29 days',leap['label'])
        self.assertEqual(leap['previous_period']['to'],'2028-02-29T23:59:59.999999+00:00')

    def test_year_boundary_and_monday(self):
        week = self.report([('2027-01-01T10:00:00+00:00',10),('2026-12-28T10:00:00+00:00',20),
                            ('2026-12-21T10:00:00+00:00',5),('2026-12-25T10:00:00+00:00',10)],
                           now='2027-01-01T12:00:00+00:00')['periods'][1]['comparison']
        self.assertEqual((week['absolute_usd'],week['percent']),(15,100))
        monday = self.report([('2027-01-04T10:00:00+00:00',10),('2026-12-28T10:00:00+00:00',5)],
                             now='2027-01-04T12:00:00+00:00')['periods'][1]['comparison']
        self.assertEqual(monday['previous_period']['to'],'2026-12-28T12:00:00+00:00')

    def test_recorded_zero_is_distinct_from_absent_baseline(self):
        today = ('2026-10-22T10:00:00+00:00',10)
        yesterday_zero = ('2026-10-21T10:00:00+00:00',0)
        zero = self.report([today,yesterday_zero])['periods'][0]['comparison']
        self.assertEqual((zero['status'],zero['absolute_usd'],zero['percent']),('zero_baseline',10,None))
        absent = self.report([today])['periods'][0]['comparison']
        self.assertEqual(absent['status'],'no_previous_data')
        self.assertIsNone(absent['absolute_usd'])
        empty = self.report([yesterday_zero])['periods'][0]['comparison']
        self.assertEqual(empty['status'],'no_current_data')
        both_zero = self.report([('2026-10-22T10:00:00+00:00',0),yesterday_zero])['periods'][0]['comparison']
        self.assertEqual((both_zero['status'],both_zero['absolute_usd'],both_zero['percent']),('available',0,0))

    def test_unknown_or_range_prices_suppress_comparison(self):
        for current,previous in [(None,10),(10,None),(None,None)]:
            comparison = self.report([('2026-10-22T10:00:00+00:00',current),
                                      ('2026-10-21T10:00:00+00:00',previous)])['periods'][0]['comparison']
            self.assertEqual(comparison['status'],'incomplete_pricing')
            self.assertIsNone(comparison['absolute_usd'])
            self.assertIsNone(comparison['percent'])
        uncertain = self.report([('2026-10-22T10:00:00+00:00',10,12),
                                 ('2026-10-21T10:00:00+00:00',10)])['periods'][0]['comparison']
        self.assertEqual(uncertain['status'],'incomplete_pricing')

    def test_dst_uses_local_clock_and_historical_midnight_offset(self):
        self.args.timezone = 'America/New_York'
        comparison = self.report([('2026-03-09T11:00:00-04:00',20),
                                  ('2026-03-08T11:59:00-04:00',10),
                                  ('2026-03-08T12:01:00-04:00',1000)],
                                 now='2026-03-09T12:00:00-04:00')['periods'][0]['comparison']
        self.assertEqual(comparison['absolute_usd'],10)
        self.assertEqual(comparison['previous_period']['from'],'2026-03-08T00:00:00-05:00')
        self.assertEqual(comparison['previous_period']['to'],'2026-03-08T12:00:00-04:00')

    def test_missing_timestamps_do_not_invent_intraday_totals(self):
        import datetime as dt
        comparison = app.menubar_comparison(
            [dict(date='2026-10-22',cost=10,cost_high=10)],'today',dt.date(2026,10,22),
            dt.datetime(2026,10,22,12,tzinfo=dt.timezone.utc),dt.timezone.utc)
        self.assertEqual(comparison['status'],'missing_timestamps')
        self.assertIsNone(comparison['absolute_usd'])


if __name__ == '__main__':
    unittest.main()
