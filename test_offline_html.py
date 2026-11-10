"""Offline loading and fallback checks using synthetic data only."""
import base64
import gzip
import json
import unittest
from html.parser import HTMLParser
import agent_usage as app


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(); self.script = False; self.text = []
    def handle_starttag(self, tag, attrs):
        if tag == 'script': self.script = True
    def handle_endtag(self, tag):
        if tag == 'script': self.script = False
    def handle_data(self, data):
        if not self.script: self.text.append(data)


class OfflineHtmlTests(unittest.TestCase):
    def test_large_snapshot_roundtrips_without_losing_fields(self):
        snapshot = {'note': '</script> Кэш & usage ' * 80000,
                    'request_stats': [{'id': 'r1', 'cost': None, 'input': 9007199254740991}]}
        output = app.render_html(snapshot)
        encoded = json.loads(output.split('<script id="snapshot" type="application/json">')[1].split('</script>')[0])
        self.assertEqual(encoded['encoding'], 'gzip-base64')
        restored = json.loads(gzip.decompress(base64.b64decode(encoded['data'])))
        self.assertEqual(restored, snapshot)
        self.assertLess(len(output), len(json.dumps(snapshot)) / 4)
        self.assertEqual(output, app.render_html(snapshot))

    def test_summary_has_values_before_scripts_and_keeps_week_boundaries(self):
        rows = [dict(date=date, session=date, requests=1, cost=cost, cost_high=cost,
                     unpriced=int(cost is None), input=100, output=10)
                for date, cost in [('2026-08-23', 99), ('2026-08-24', 2),
                                   ('2026-08-30', 3), ('2026-08-31', 5),
                                   ('2026-09-05', None), ('2026-09-06', 100)]]
        output = app.render_html(dict(as_of_date='2026-09-05',rows=rows,price_basis='current_rates'))
        summary = output.split('<section id="saved-summary"')[1].split('</section>')[0]
        cards = summary.split('<article')[1:]
        self.assertEqual(len(cards), 4)
        self.assertNotIn(' + ?',summary)
        self.assertIn('$8.00', cards[0])
        self.assertIn('$5.00', cards[1])
        self.assertIn('2026-08-31 – 2026-09-05', cards[1])
        self.assertIn('$5.00', cards[2])
        self.assertIn('2026-08-24 – 2026-08-30', cards[2])
        self.assertIn('$209.00', cards[3])
        parser = VisibleText(); parser.feed(summary)
        self.assertIn('1 requests excluded from cost.', ''.join(parser.text))
        self.assertIn('<div id="interactive-dashboard" hidden>', output)
        self.assertLess(output.index('Saved usage summary'), output.index('<script id="snapshot"'))

    def test_empty_and_unpriced_summaries_do_not_claim_zero_cost(self):
        for rows in [[], [dict(date='2026-09-05',session='s',requests=1,unpriced=1,cost=0)]]:
            summary = app.saved_summary(dict(as_of_date='2026-09-05',rows=rows))
            self.assertNotIn('$0.00', summary)
            self.assertIn('—', summary)

    def test_fallback_identifies_the_price_source(self):
        for basis, label in [('models_dev_rates', 'models.dev rates for all dates'),
                             ('current_rates', 'Current rates for all dates'),
                             ('custom_rates', 'Custom rates')]:
            with self.subTest(basis=basis):
                summary = app.saved_summary(dict(as_of_date='2026-10-22', price_basis=basis))
                self.assertIn(label, summary)
                if basis != 'custom_rates':
                    self.assertNotIn('Custom rates', summary)

    def test_model_fit_reaches_the_page_under_the_offline_rules(self):
        hostile = '</script><img src=x onerror=alert(1)>'
        unit = dict(kind='turn', session='Claude:s', main_session='Claude:s', n=1, project='p', date='2026-09-05',
                    ts=1788600000, tier='opus', model='claude-opus-5-5', effort='high', title=hostile, cost=1.5)
        model_fit = dict(schema=1, guide=[], units=[unit], note=hostile,
                         events=dict(switches=[], cold=[], effort_changes=[], daily=[]))
        csp = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; "
               "img-src data:; base-uri 'none'; form-action 'none'")
        for units in (1, 6000):  # the second one is over 1 MB and goes through the gzip loader
            with self.subTest(units=units):
                snapshot = dict(as_of_date='2026-09-05', rows=[], model_fit=dict(model_fit, units=[unit] * units))
                output = app.render_html(snapshot)
                embedded = output.split('<script id="snapshot" type="application/json">')[1].split('</script>')[0]
                self.assertNotIn('<', embedded)
                data = json.loads(embedded)
                if data.get('encoding') == 'gzip-base64':
                    data = json.loads(gzip.decompress(base64.b64decode(data['data'])))
                else:
                    self.assertEqual(units, 1)
                self.assertEqual(data['model_fit'], snapshot['model_fit'])
                self.assertIn(f'<meta http-equiv="Content-Security-Policy" content="{csp}">', output)
                self.assertIn('data-tab="fit"', output)
                self.assertIn('id="view-fit"', output)
                self.assertNotIn(hostile, output)
        script = app.HTML.split('</script><script>')[1].split('</script>')[0]
        for network in ('fetch(', 'XMLHttpRequest', 'WebSocket', 'EventSource', 'sendBeacon', 'import('):
            self.assertNotIn(network, script)
        # The Model fit view builds its DOM from text nodes only.
        section = script.split('// Model fit tab.')[1].split('function render(){')[0]
        for markup in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write'):
            self.assertNotIn(markup, section)

    def test_fallback_text_is_escaped(self):
        summary=app.saved_summary(dict(as_of_date='2026-09-05',generated='<img src=x onerror=alert(1)>'))
        self.assertNotIn('<img', summary)
        self.assertIn('&lt;img', summary)


if __name__ == '__main__':
    unittest.main()
