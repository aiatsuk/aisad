"""Published-rate refresh: what it imports, what it keeps, and what it refuses."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import agent_usage as app


def published(**overrides):
    """A minimal models.dev payload shaped like the public catalog."""
    payload = {
        'anthropic': {'models': {
            'claude-opus-5': {'cost': {'input': 5, 'output': 25, 'cache_read': 0.5, 'cache_write': 6.25},
                              'experimental': {'modes': {'fast': {'cost': {'input': 10, 'output': 50}}}}},
        }},
        'openai': {'models': {
            'gpt-6-astra': {'cost': {'input': 10, 'output': 50, 'cache_read': 1, 'cache_write': 12.5,
                                     'tiers': [{'input': 20, 'output': 75, 'tier': {'type': 'context', 'size': 272000}}]},
                            'experimental': {'modes': {'fast': {'cost': {'input': 20, 'output': 100}}}}},
            'newly-published-model': {'cost': {'input': 3, 'output': 9, 'cache_read': 0.3}},
            'image-only-model': {'cost': {}},
        }},
        'some-reseller': {'models': {
            'claude-opus-5': {'cost': {'input': 99, 'output': 99, 'cache_read': 99, 'cache_write': 99}},
        }},
    }
    payload.update(overrides)
    return payload


class FakeResponse(io.BytesIO):
    def __init__(self, body, etag=None):
        super().__init__(body)
        self.headers = {'ETag': etag} if etag else {}

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()


class PriceRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aisad prices ')
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'report'

    def refresh(self, payload=None, etag='"one"', body=None):
        data = body if body is not None else json.dumps(payload if payload is not None else published()).encode()
        with patch('urllib.request.urlopen', return_value=FakeResponse(data, etag)) as opened:
            result = app.refresh_prices(self.output)
        return result, opened

    def catalog(self):
        return json.loads((self.output / app.PRICE_CACHE).read_text())

    def test_published_rates_reproduce_the_built_in_table(self):
        self.refresh()
        catalog = self.catalog()
        built_in = app.default_prices()['models']
        for model in ('claude-opus-5', 'gpt-6-astra'):
            for field in ('input', 'output', 'cached', 'write_5m'):
                self.assertEqual(catalog['models'][model][field], built_in[model][field], (model, field))
        self.assertEqual(catalog['models']['gpt-6-astra']['fast_multiplier'], 2)
        self.assertEqual(catalog['models']['gpt-6-astra']['long_threshold'], 272000)
        self.assertEqual(catalog['models']['gpt-6-astra']['long_input_multiplier'], 2)
        self.assertEqual(catalog['models']['gpt-6-astra']['long_output_multiplier'], 1.5)
        self.assertEqual(catalog['basis'], 'models_dev_rates')
        self.assertIn(app.MODELS_DEV_URL, catalog['sources'])

    def test_fields_the_source_omits_survive_the_refresh(self):
        self.refresh()
        rule = self.catalog()['models']['gpt-6-astra']
        built_in = app.default_prices()['models']['gpt-6-astra']
        # models.dev publishes neither one-hour cache writes nor the discounts.
        self.assertEqual(rule['write_1h'], built_in['write_1h'])
        self.assertEqual(rule['flex_multiplier'], built_in['flex_multiplier'])
        self.assertEqual(rule['batch_multiplier'], built_in['batch_multiplier'])

    def test_a_model_missing_from_the_source_keeps_its_built_in_rate(self):
        self.refresh(payload={'anthropic': published()['anthropic'], 'openai': {'models': {}}})
        catalog = self.catalog()
        for model, rule in app.default_prices()['models'].items():
            self.assertIn(model, catalog['models'], model)
        self.assertEqual(catalog['models']['gpt-6-astra'], app.default_prices()['models']['gpt-6-astra'])

    def test_new_models_arrive_and_unpriced_cache_writes_stay_unpriced(self):
        self.refresh()
        rule = self.catalog()['models']['newly-published-model']
        self.assertEqual((rule['input'], rule['output'], rule['cached']), (3, 9, 0.3))
        self.assertEqual(rule['write_5m'], 0)
        self.assertTrue(rule['no_cache_write_rate'])
        self.assertNotIn('image-only-model', self.catalog()['models'])

    def test_only_first_party_providers_are_read(self):
        self.refresh()
        self.assertEqual(self.catalog()['models']['claude-opus-5']['input'], 5)

    def test_revalidation_sends_the_stored_tag_and_keeps_the_catalog(self):
        self.refresh(etag='"one"')
        first = self.catalog()
        error = urllib.error.HTTPError(app.MODELS_DEV_URL, 304, 'Not Modified', {}, None)
        with patch('urllib.request.urlopen', side_effect=error) as opened:
            result = app.refresh_prices(self.output)
        self.assertEqual(result['status'], 'revalidated')
        self.assertEqual(self.catalog(), first)
        request = opened.call_args[0][0]
        self.assertEqual(request.get_header('If-none-match'), '"one"')
        meta = json.loads((self.output / app.PRICE_CACHE_META).read_text())
        self.assertEqual(meta['etag'], '"one"')
        self.assertTrue(meta['checked_at'])

    def test_a_rejected_payload_leaves_the_previous_catalog_in_place(self):
        self.refresh()
        first = self.catalog()
        for payload in ({'anthropic': {'models': {}}, 'openai': {'models': {}}}, {'anthropic': {}, 'openai': {}}, []):
            with patch('urllib.request.urlopen', return_value=FakeResponse(json.dumps(payload).encode(), '"two"')):
                with self.assertRaises(ValueError):
                    app.refresh_prices(self.output)
            self.assertEqual(self.catalog(), first)

    def test_an_oversized_response_is_refused(self):
        body = b'{"anthropic": "' + b'x' * (app.MODELS_DEV_LIMIT + 10) + b'"}'
        with patch('urllib.request.urlopen', return_value=FakeResponse(body, '"big"')):
            with self.assertRaises(ValueError):
                app.refresh_prices(self.output)
        self.assertFalse((self.output / app.PRICE_CACHE).exists())

    def test_reports_use_refreshed_rates_and_a_corrupt_cache_falls_back(self):
        self.refresh()
        catalog = app.load_prices(None, self.output)
        self.assertEqual(catalog['basis'], 'models_dev_rates')
        (self.output / app.PRICE_CACHE).write_text('{"currency": "EUR"}')
        catalog = app.load_prices(None, self.output)
        self.assertEqual(catalog['basis'], 'current_rates')
        self.assertEqual(catalog['as_of'], app.PRICE_DATE)

    def test_an_explicit_catalog_still_wins(self):
        self.refresh()
        custom = Path(self.temp.name) / 'custom.json'
        custom.write_text(json.dumps(dict(app.default_prices(), as_of='2020-01-01', basis='custom_rates')))
        self.assertEqual(app.load_prices(str(custom), self.output)['as_of'], '2020-01-01')

    def test_only_the_prices_command_may_reach_the_network(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('Network used')):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                app.main(['prices', '--output', str(self.output), '--json'])
            self.assertEqual(json.loads(out.getvalue())['status'], 'local')
            with self.assertRaises(SystemExit):
                app.main(['usage', '--refresh', '--output', str(self.output)])


if __name__ == '__main__':
    unittest.main()
