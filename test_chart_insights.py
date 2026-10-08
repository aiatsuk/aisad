"""Deterministic week totals, color levels and known-cost forecasts."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

import agent_usage as app


class ChartInsightsTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.args=app.parser().parse_args(['chart','--output',temporary.name])

    def snapshot(self, daily, today='2026-10-08', provider='Claude'):
        rows=[];records=[]
        for date,cost in daily:
            rows.append(dict(date=date,cost=cost or 0,cost_high=cost or 0,provider=provider,requests=1,unpriced=int(cost is None),
                model='claude-opus-5',project='synthetic',role='main',pool='interactive'))
            records.append(dict(date=date,cost=cost,cost_high=cost,provider=provider))
        return dict(as_of_date=today,generated=today+'T12:00:00Z',timezone='UTC',rows=rows,request_stats=records,grok_records=[])

    def history(self, cost):
        first=dt.date(2026,9,10)
        return [(str(first+dt.timedelta(days=index)),cost(first+dt.timedelta(days=index))) for index in range(28)]

    def test_week_totals_preserve_zero_unknown_and_partial_weeks(self):
        report=app.terminal_chart_report(self.snapshot([('2026-10-01',10),('2026-10-02',0),('2026-10-03',None)]),self.args)
        total=report['weekday_view']['totals'][0]
        self.assertEqual((total['cost_usd'],total['observations'],total['unpriced_observations'],total['priced_days']),(10,3,1,2))
        self.assertTrue(total['incomplete'])
        self.assertIsNone(report['weekday_view']['totals'][2]['cost_usd'])
        text=app.terminal_week_text(report,width=100)
        totals=[line for line in text.splitlines() if line.startswith('Total      ')]
        self.assertEqual(len(totals),1);self.assertIn('$10.00',totals[0]);self.assertIn('—',totals[0])
        unknown=app.terminal_chart_report(self.snapshot([('2026-10-01',None)]),self.args)
        self.assertIsNone(unknown['weekday_view']['totals'][0]['cost_usd'])
        self.assertIn('?',next(line for line in app.terminal_week_text(unknown).splitlines() if line.startswith('Total      ')))

    def test_five_intensity_levels_and_observed_zero(self):
        report=app.terminal_chart_report(self.snapshot([(f'2026-10-{index+1:02d}',cost) for index,cost in enumerate([20,40,60,80,100,0,None])]),self.args)
        levels={cell['date']:cell['intensity_level'] for row in report['weekday_view']['rows'] for cell in row['cells'] if cell['in_month']}
        self.assertEqual([levels[f'2026-10-{day:02d}'] for day in range(1,8)],[0,1,2,3,4,0,None])
        colored=app.terminal_week_text(report,color=True)
        for tone in app.SPEND_COLORS:self.assertIn('\x1b[38;2;'+tone+'m',colored)

    def test_forecast_reaches_october_18_in_ten_days(self):
        history=self.history(lambda date:100)
        snapshot=self.snapshot(history+[('2026-10-08',300),('2026-10-09',5000)])
        report=app.terminal_chart_report(snapshot,self.args)
        insight=report['insights'];forecast=insight['forecast']
        self.assertEqual(insight['window'],{'from':'2026-09-10','to':'2026-10-07','days':28})
        self.assertEqual(forecast['status'],'projected_limit');self.assertEqual(forecast['limit_date'],'2026-10-18')
        self.assertEqual(forecast['days_until_limit'],10);self.assertAlmostEqual(forecast['projected_month_cost_usd'],3300)
        self.assertIn('Oct 18 (in 10 days)',insight['messages'][0])

    def test_month_reset_closed_month_and_reached_budget(self):
        snapshot=self.snapshot(self.history(lambda date:10)+[('2026-10-08',10)])
        forecast=app.terminal_chart_report(snapshot,self.args)['insights']['forecast']
        self.assertEqual(forecast['status'],'within_budget');self.assertIsNone(forecast['limit_date'])
        self.assertAlmostEqual(forecast['projected_month_cost_usd'],310)
        closed=app.terminal_chart_report(snapshot,self.args,'2026-09')['insights']
        self.assertEqual(closed['forecast']['status'],'closed_month');self.assertEqual(closed['window']['to'],'2026-09-30')
        reached=app.terminal_chart_report(self.snapshot([('2026-10-08',2100)]),self.args)['insights']['forecast']
        self.assertEqual((reached['status'],reached['days_until_limit']),('reached',0))

    def test_absent_unpriced_and_observed_zero_are_distinct(self):
        for daily in [[],[('2026-10-01',None)],[('2026-10-01',50)]]:
            report=app.terminal_chart_report(self.snapshot(daily),self.args)
            self.assertEqual(report['insights']['forecast']['status'],'insufficient_data')
            self.assertIsNone(report['insights']['forecast']['projected_month_cost_usd'])
        zero=app.terminal_chart_report(self.snapshot(self.history(lambda date:0)+[('2026-10-08',0)]),self.args)
        self.assertEqual(zero['insights']['forecast']['status'],'within_budget')
        self.assertEqual(zero['insights']['forecast']['projected_month_cost_usd'],0)
        closed=app.terminal_chart_report(self.snapshot([]),self.args,'2026-09')
        self.assertIn('unavailable',closed['insights']['messages'][0]);self.assertNotIn('$0.00',closed['insights']['messages'][0])

    def test_weekday_insight_uses_four_weeks_and_budget_ignores_filters(self):
        snapshot=self.snapshot(self.history(lambda date:300 if date.weekday()==1 else 200 if date.weekday()==2 else 10))
        report=app.terminal_chart_report(snapshot,self.args)
        self.assertEqual([row['weekday'] for row in report['insights']['busiest_weekdays']],['Tuesday','Wednesday'])
        self.assertEqual([row['observed_days'] for row in report['insights']['busiest_weekdays']],[4,4])
        self.assertEqual([row['average_cost_usd'] for row in report['insights']['busiest_weekdays']],[300,200])
        self.args.project='absent'
        filtered=app.terminal_chart_report(snapshot,self.args)
        self.assertEqual(filtered['insights']['busiest_weekdays'],[])
        self.assertEqual(filtered['insights']['forecast'],report['insights']['forecast'])

    def test_recent_days_have_more_forecast_weight(self):
        snapshot=self.snapshot(self.history(lambda date:100 if date>=dt.date(2026,10,1) else 10)+[('2026-10-08',100)])
        report=app.terminal_chart_report(snapshot,self.args)
        unweighted=report['monthly_budget']['known_cost_usd']+23*(21*10+7*100)/28
        self.assertGreater(report['insights']['forecast']['projected_month_cost_usd'],unweighted)

    def test_ui_dataset_retains_cross_month_history_and_is_aggregate_only(self):
        snapshot=self.snapshot(self.history(lambda date:100)+[('2026-10-08',300)])
        report=app.terminal_chart_report(snapshot,self.args)
        dataset=app.terminal_ui_dataset(snapshot,self.args)
        october=next(month['report'] for month in dataset['months'] if month['month']=='2026-10')
        self.assertEqual(october['insights'],report['insights'])
        self.assertEqual(october['weekday_view']['totals'],report['weekday_view']['totals'])


if __name__=='__main__':unittest.main()
