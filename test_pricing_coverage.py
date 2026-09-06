"""Pricing regression cases; synthetic metadata only."""
import unittest
import agent_usage as app


class PricingCoverageTests(unittest.TestCase):
    def row(self, model, **changes):
        row = dict(model=model, provider='Codex', ts=1788600000, tier='standard',
                   speed='standard', geo='global', web_searches=0)
        row.update(app.normalize_usage(dict(input_tokens=1000000,
                       cached_input_tokens=800000, output_tokens=100000), 'Codex'))
        row.update(changes)
        return row

    def test_published_legacy_codex_rates_use_uncached_and_cached_components(self):
        # Published USD / 1M: 200K fresh + 800K cached + 100K output.
        for model, expected in [('gpt-5-codex', 1.35), ('gpt-5.1-codex', 1.35),
                                ('gpt-5.1-codex-mini', .27), ('gpt-5.1-codex-max', 1.35),
                                ('gpt-5.2-codex', 1.89)]:
            with self.subTest(model=model):
                result = app.price_request(self.row(model), app.default_prices())
                self.assertAlmostEqual(result['cost'], expected)
                self.assertEqual(result['price_status'], 'priced')

    def test_service_and_missing_models_are_not_guessed_or_zeroed(self):
        for model in ['codex-auto-review', 'unknown', 'gpt-5.3-codex-spark', 'local-model']:
            result = app.price_request(self.row(model), app.default_prices())
            self.assertIsNone(result['cost'])
        result = app.price_request(self.row('gpt-5.2-codex', tier='priority'), app.default_prices())
        self.assertIsNone(result['cost'])
        self.assertEqual(result['price_status'], 'unpriced_tier')

    def test_gap_counts_preserve_tokens_and_distinguish_reasons(self):
        records = []
        for model, extra in [('codex-auto-review', {}), ('codex-auto-review', {}),
                             ('unknown', {}), ('gpt-5.2-codex', {'tier': 'priority'}),
                             ('gpt-5.2-codex', {})]:
            row = self.row(model, **extra)
            row.update(app.price_request(row, app.default_prices()))
            records.append(row)
        result = app.pricing_coverage(records)
        self.assertEqual((result['observed_requests'], result['priced_requests'],
                          result['unpriced_requests']), (5, 1, 4))
        self.assertEqual(result['unpriced_groups'][0]['reason'], 'internal_model')
        self.assertEqual(result['unpriced_groups'][0]['requests'], 2)
        self.assertEqual(result['unpriced_groups'][0]['input_tokens'], 2000000)
        self.assertEqual({g['reason'] for g in result['unpriced_groups']},
                         {'internal_model', 'missing_model', 'unpriced_tier'})
        self.assertEqual(app.pricing_coverage(records[-1:])['unpriced_groups'], [])

    def test_statistics_keep_pricing_status_and_usage_json_exposes_coverage(self):
        row = self.row('codex-auto-review', id='x', session='Codex:s', date='2026-09-05',
                       project='example', role='review')
        row.update(app.price_request(row, app.default_prices()))
        stats = app.request_statistics([row])
        self.assertEqual(stats[0]['price_status'], 'unknown_model')
        period = app.usage_period([], request_stats=stats)
        self.assertEqual(period['pricing_coverage']['unpriced_groups'][0]['model'], 'codex-auto-review')


if __name__ == '__main__':
    unittest.main()
