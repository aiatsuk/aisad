"""Frozen weekly and monthly forecasts with a suggested budget target (synthetic data only)."""
import datetime as dt
import json
import random
import tempfile
import unittest
from pathlib import Path

import agent_usage as app

D=dt.date


class ForecastTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.output=temporary.name

    def run_cli(self,*arguments):
        return app.parser().parse_args(list(arguments)+['--output',self.output])

    def snapshot(self,daily,today):
        records=[dict(date=str(date),cost=cost,cost_high=cost,provider='Claude') for date,cost in daily]
        return dict(as_of_date=str(today),generated=str(today)+'T12:00:00Z',timezone='UTC',price_as_of='synthetic',request_stats=records)

    def weekdays(self,start,end,cost):
        """A steady cost on Monday-Friday; weekends have no requests (idle)."""
        out=[];day=start
        while day<=end:
            if day.weekday()<5:out.append((day,cost(day) if callable(cost) else cost))
            day+=dt.timedelta(1)
        return out

    def enable(self,*extra):
        app.budget_command(self.run_cli('budget','--forecast','on',*extra))

    def test_settings_roundtrip_and_validation(self):
        self.assertEqual(app.budget_command(self.run_cli('budget'))['forecast'],dict(enabled=False,quantile=.8))
        result=app.budget_command(self.run_cli('budget','--forecast','on','--quantile','0.9','--set','1500'))
        self.assertEqual((result['forecast'],result['monthly_budget_usd']),(dict(enabled=True,quantile=.9),1500))
        self.assertEqual(app.budget_command(self.run_cli('budget','--forecast','off'))['forecast']['enabled'],False)
        with self.assertRaises(ValueError):app.budget_command(self.run_cli('budget','--quantile','0.2'))
        Path(self.output,'budget.json').write_text(json.dumps(dict(forecast_enabled='yes')))
        with self.assertRaises(ValueError):app.budget_command(self.run_cli('budget'))

    def test_day_semantics_idle_is_zero_but_unpriced_and_pre_history_are_missing(self):
        days,first=app.forecast_days(self.snapshot([(D(2026,9,7),10.),(D(2026,9,9),None)],D(2026,9,12)))
        value=lambda day:app.forecast_value(days,first,day)
        self.assertEqual((value(D(2026,9,7)),value(D(2026,9,8))),(10.,0.))
        self.assertIsNone(value(D(2026,9,9)))
        self.assertIsNone(value(D(2026,9,6)))

    def test_constant_weekday_spend_is_forecast_exactly_including_idle_weekends(self):
        daily=self.weekdays(D(2026,8,3),D(2026,9,30),100.)
        days,first=app.forecast_days(self.snapshot(daily,D(2026,10,1)))
        week=app.forecast_period(days,first,D(2026,9,28),D(2026,10,5),.8)
        self.assertEqual(week['status'],'ok');self.assertAlmostEqual(week['forecast_usd'],500,delta=.5)
        month=app.forecast_period(days,first,D(2026,10,1),D(2026,11,1),.8)
        self.assertAlmostEqual(month['forecast_usd'],22*100,delta=.5)  # October 2026 has 22 weekdays and 9 idle weekend days
        self.assertGreaterEqual(month['target_usd'],month['forecast_usd'])

    def test_month_length_is_calendar_exact(self):
        daily=[(D(2026,1,1)+dt.timedelta(i),50.) for i in range(120)]
        days,first=app.forecast_days(self.snapshot(daily,D(2026,5,1)))
        february=app.forecast_period(days,first,D(2026,2,1),D(2026,3,1),.8)['forecast_usd']
        march=app.forecast_period(days,first,D(2026,3,1),D(2026,4,1),.8)['forecast_usd']
        self.assertAlmostEqual(february,28*50,delta=1);self.assertAlmostEqual(march,31*50,delta=1)

    def test_insufficient_history_is_refused_with_reasons(self):
        days,first=app.forecast_days(self.snapshot(self.weekdays(D(2026,9,14),D(2026,9,27),20.),D(2026,9,28)))
        result=app.forecast_period(days,first,D(2026,9,28),D(2026,10,5),.8)
        self.assertEqual(result['status'],'insufficient_data');self.assertTrue(any('complete Monday-Sunday weeks' in r for r in result['reasons']))
        days,first=app.forecast_days(self.snapshot([(D(2026,9,1)+dt.timedelta(7*i),20.) for i in range(6)],D(2026,10,12)))
        self.assertTrue(any('last 21 days' in r for r in app.forecast_period(days,first,D(2026,10,12),D(2026,10,19),.8)['reasons']))
        self.assertEqual(app.forecast_period({},None,D(2026,10,12),D(2026,10,19),.8)['status'],'insufficient_data')

    def test_level_shift_and_pricing_gaps_lower_confidence(self):
        daily=self.weekdays(D(2026,6,1),D(2026,9,20),10.)+self.weekdays(D(2026,9,21),D(2026,9,27),100.)
        days,first=app.forecast_days(self.snapshot(daily,D(2026,9,28)))
        shifted=app.forecast_period(days,first,D(2026,9,28),D(2026,10,5),.8)
        self.assertIn('level_shift_suspected',shifted['flags']);self.assertEqual(shifted['confidence'],'low')
        unpriced=[(day,None) for day,_ in self.weekdays(D(2026,6,1),D(2026,9,27),1.)][::2]
        days,first=app.forecast_days(self.snapshot(self.weekdays(D(2026,6,1),D(2026,9,27),10.)+unpriced,D(2026,9,28)))
        self.assertIn('low_pricing_coverage',app.forecast_period(days,first,D(2026,9,28),D(2026,10,5),.8)['flags'])

    def test_spread_uses_student_t_and_is_not_shrunk_by_square_root_of_weeks(self):
        self.assertAlmostEqual(app.t_quantile(.8,7),.896,places=2);self.assertAlmostEqual(app.t_quantile(.9,7),1.415,places=2)
        self.assertAlmostEqual(app.t_quantile(.9,2),1.886,places=2);self.assertAlmostEqual(app.t_quantile(.9,1),3.078,places=2)
        self.assertAlmostEqual(app.forecast_spread([100,100,100,100]),(4*.35**2/7)**.5)  # a constant series keeps part of the prior spread, not zero
        self.assertGreater(app.forecast_spread([10,400,40,900]),app.forecast_spread([100,110,95,105]))

    def test_disabled_forecast_writes_nothing(self):
        args=self.run_cli('forecast')
        result=app.forecast_command(self.snapshot(self.weekdays(D(2026,6,1),D(2026,9,27),30.),D(2026,9,28)),args)
        self.assertEqual(result['status'],'disabled');self.assertFalse(Path(self.output,'forecast.json').exists())

    def test_forecast_is_frozen_for_the_period_and_closed_with_an_actual(self):
        self.enable();args=self.run_cli('forecast')
        history=self.weekdays(D(2026,6,1),D(2026,9,27),30.)
        first=app.forecast_command(self.snapshot(history,D(2026,9,28)),args)
        self.assertEqual(first['status'],'ok');frozen=first['week']['forecast_usd'];target=first['week']['target_usd']
        ledger=json.loads(Path(self.output,'forecast.json').read_text())
        self.assertEqual(ledger['schema_version'],1);self.assertEqual(set(ledger['entries']),{'week:2026-09-28','month:2026-09'})
        # Spending triples mid-week: the stored forecast and target must not move, while pace reacts.
        surge=history+[(D(2026,9,28),300.),(D(2026,9,29),300.)]
        later=app.forecast_command(self.snapshot(surge,D(2026,9,30)),args)
        self.assertEqual((later['week']['forecast_usd'],later['week']['target_usd']),(frozen,target))
        self.assertEqual(later['week']['actual_to_date_usd'],600);self.assertGreater(later['week']['pace_usd'],frozen)
        self.assertEqual(later['week']['frozen_at'],first['week']['frozen_at'])
        # The next week gets its own forecast; the finished week records its actual once and keeps its forecast.
        week_two=app.forecast_command(self.snapshot(surge+self.weekdays(D(2026,9,30),D(2026,10,2),300.),D(2026,10,5)),args)
        closed=json.loads(Path(self.output,'forecast.json').read_text())['entries']['week:2026-09-28']
        self.assertEqual((closed['forecast_usd'],closed['actual_usd']),(frozen,600+3*300))
        self.assertIn('week:2026-10-05',json.loads(Path(self.output,'forecast.json').read_text())['entries'])
        self.assertGreaterEqual(week_two['accuracy']['closed_periods'],1)

    def test_unsupported_ledger_version_is_preserved(self):
        self.enable();Path(self.output,'forecast.json').write_text(json.dumps(dict(schema_version=9,entries={})))
        with self.assertRaises(ValueError):
            app.forecast_command(self.snapshot(self.weekdays(D(2026,6,1),D(2026,9,27),30.),D(2026,9,28)),self.run_cli('forecast'))
        self.assertEqual(json.loads(Path(self.output,'forecast.json').read_text())['schema_version'],9)

    def test_calibration_switches_from_formula_to_replayed_history(self):
        short=self.weekdays(D(2026,9,7),D(2026,9,27),30.)
        days,first=app.forecast_days(self.snapshot(short,D(2026,9,28)))
        self.assertEqual(app.forecast_period(days,first,D(2026,9,28),D(2026,10,5),.8)['calibration']['state'],'uncalibrated')
        rng=random.Random(7);long=self.weekdays(D(2026,3,2),D(2026,9,27),lambda d:30*rng.lognormvariate(0,.5))
        days,first=app.forecast_days(self.snapshot(long,D(2026,9,28)))
        result=app.forecast_period(days,first,D(2026,9,28),D(2026,10,5),.8)
        self.assertEqual((result['calibration']['state'],result['calibration']['basis']),('calibrated','replayed_history'))
        self.assertGreaterEqual(result['calibration']['ratios'],app.FORECAST_MIN_RATIOS)

    def test_seeded_synthetic_backtest_stays_roughly_unbiased_and_covers_the_target(self):
        """Regression range, not an accuracy claim: weekday profile + AR(1) level + lognormal noise."""
        bias_total=actual_total=0.;hits=[];checked=0
        for seed in range(12):
            rng=random.Random(seed);level=0.;daily=[];start=D(2026,1,5)
            for i in range(26*7):
                day=start+dt.timedelta(i);level=.85*level+rng.gauss(0,.18)
                factor=(1,1.2,1.2,1,.9,.1,.05)[day.weekday()]
                if rng.random()<.04:continue
                daily.append((day,40*factor*rng.lognormvariate(0,.6)*(2.718281828**level)))
            days,first=app.forecast_days(self.snapshot(daily,D(2026,7,6)))
            for week in range(10,25):
                monday=start+dt.timedelta(7*week);result=app.forecast_period(days,first,monday,monday+dt.timedelta(7),.8)
                if result['status']!='ok':continue
                actual=sum(app.forecast_value(days,first,monday+dt.timedelta(i)) or 0. for i in range(7))
                bias_total+=result['forecast_usd']-actual;actual_total+=actual;hits.append(actual<=result['target_usd']);checked+=1
        self.assertGreater(checked,100)
        self.assertLess(abs(bias_total/actual_total),.2)
        self.assertTrue(.65<=sum(hits)/len(hits)<=.97,sum(hits)/len(hits))


if __name__=='__main__':
    unittest.main()
