"""Large histories: bounded snapshot parts and the event preview budget. Synthetic data only."""
import base64
import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent_usage as app


def unpack(packed):
    """Rebuild a snapshot the way the page's decodeSnapshot does."""
    if packed.get('encoding') == 'gzip-base64':
        return json.loads(gzip.decompress(base64.b64decode(packed['data'])))
    if packed.get('encoding') != 'gzip-base64-parts':
        return packed
    assert packed['format'] == 1 and len(packed['parts']) == len(packed['data']) > 0
    result = {}
    for part, blob in zip(packed['parts'], packed['data']):
        value = json.loads(gzip.decompress(base64.b64decode(blob)))
        if part['kind'] == 'keys':
            assert isinstance(value, dict) and len(value) == part['count']
            result.update(value)
        elif part['kind'] == 'items':
            assert isinstance(value, list) and len(value) == part['count']
            result.setdefault(part['key'], []).extend(value)
        elif part['kind'] == 'entries':
            assert isinstance(value, dict) and len(value) == part['count']
            result.setdefault(part['key'], {}).update(value)
        else:
            raise AssertionError('unknown part kind ' + repr(part['kind']))
    return result


def part_texts(packed):
    return [gzip.decompress(base64.b64decode(blob)).decode('utf-8') for blob in packed['data']]


def embedded(page):
    return json.loads(page.split('<script id="snapshot" type="application/json">')[1].split('</script>')[0])


def synthetic(sessions=300, requests=3000):
    """Every shape the snapshot has: big lists and objects, small keys, text a page must escape."""
    ids = ['Claude:s%03d' % n if n % 2 else 'Codex:s%03d' % n for n in range(sessions)]
    request_stats = [dict(id='r%05d' % n, session=ids[n % sessions], ts=1788600000 + n, date='2026-09-05', provider='Claude',
                          project='p', role='main', pool='interactive', requests=1, unpriced=int(n % 97 == 0),
                          cost=None if n % 97 == 0 else n / 7, cost_high=None if n % 97 == 0 else n / 7,
                          input=9007199254740991 if n == 5 else n * 1000, output=n, cached=0, write=0, total=n,
                          model='Кэш </script> & "model"', evidence=[dict(line=n, source_id='a' * 64)]) for n in range(requests)]
    previews = {sid: [dict(kind='usage', ts=1788600000 + n * 60 + k, tool=None, date='2026-09-05') for k in range(5)]
                for n, sid in enumerate(ids)}
    return dict(version='test', generated='2026-09-05T12:00:00+00:00', as_of_date='2026-09-05', timezone='UTC',
                summary=dict(requests=requests, cost=1.5), quality={}, titles={ids[1]: 'Заголовок 🚀 <b>'},
                rows=[dict(date='2026-09-05', session=sid, requests=1, cost=1.0) for sid in ids[:50]],
                request_stats=request_stats, session_details=[dict(id=sid, children=[], event_count=5) for sid in ids],
                event_previews=dict(previews, **{'Claude:omitted': None}), grok_records=[], unknown_models=[],
                live_updates=True, demo=False, model_fit=dict(schema=1, units=[], note='x' * 500))


class SnapshotPartsTests(unittest.TestCase):
    def test_parts_round_trip_and_each_part_stays_within_the_bound(self):
        snapshot = synthetic()
        whole = len(json.dumps(snapshot, separators=(',', ':')))
        limit = 4000
        packed = app.pack_snapshot(snapshot, limit)
        self.assertEqual(packed['encoding'], 'gzip-base64-parts')
        self.assertEqual(packed['format'], 1)
        self.assertGreater(whole, 100 * limit)
        self.assertGreater(len(packed['parts']), 100)
        texts = part_texts(packed)
        for text in texts:
            self.assertLessEqual(len(text), limit)
            self.assertTrue(text.isascii())
            json.loads(text)
        self.assertEqual({p['kind'] for p in packed['parts']}, {'keys', 'items', 'entries'})
        self.assertEqual({p['key'] for p in packed['parts'] if p['kind'] != 'keys'},
                         {'request_stats', 'event_previews', 'session_details'})
        self.assertEqual(unpack(packed), snapshot)
        self.assertEqual(packed, app.pack_snapshot(snapshot, limit))  # deterministic

    def test_a_single_item_larger_than_a_part_gets_a_part_of_its_own(self):
        snapshot = dict(small=1, request_stats=[dict(text='y' * 50)] * 3 + [dict(text='z' * 900)])
        packed = app.pack_snapshot(snapshot, 200)
        self.assertEqual(unpack(packed), snapshot)
        self.assertEqual([len(t) > 200 for t in part_texts(packed)].count(True), 1)

    def test_small_and_one_part_snapshots_keep_the_existing_forms(self):
        small = dict(as_of_date='2026-09-05', rows=[], note='Кэш')
        self.assertIsNone(app.pack_snapshot(small))
        self.assertEqual(embedded(app.render_html(small)), small)
        medium = dict(as_of_date='2026-09-05', rows=[], note='x' * 1_200_000)
        self.assertEqual(embedded(app.render_html(medium))['encoding'], 'gzip-base64')
        self.assertEqual(unpack(embedded(app.render_html(medium))), medium)

    def test_render_html_embeds_parts_safely_and_the_override_forces_them(self):
        snapshot = synthetic(40, 400)
        for kwargs, env in (({'part_chars': 3000}, {}), ({}, {'ASI_SNAPSHOT_PART_CHARS': '3000'})):
            with self.subTest(kwargs=kwargs, env=env), patch.dict(os.environ, env):
                page = app.render_html(snapshot, **kwargs)
                raw = page.split('<script id="snapshot" type="application/json">')[1].split('</script>')[0]
                self.assertNotIn('<', raw)
                data = json.loads(raw)
                self.assertEqual(data['encoding'], 'gzip-base64-parts')
                self.assertTrue(all(len(t) <= 3000 for t in part_texts(data)))
                self.assertEqual(unpack(data), snapshot)
                self.assertLess(page.index('Saved usage summary'), page.index('<script id="snapshot"'))
                self.assertEqual(page, app.render_html(snapshot, **kwargs))
        for value in ('0', '-5', 'abc', '1e3', '', '1' + '0' * 400):
            with self.subTest(value=value), patch.dict(os.environ, {'ASI_SNAPSHOT_PART_CHARS': value}):
                self.assertEqual(app.snapshot_part_chars(), app.SNAPSHOT_PART_CHARS)
                self.assertNotEqual(embedded(app.render_html(snapshot)).get('encoding'), 'gzip-base64-parts')


class LiveFileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name)
        self.args = app.parser().parse_args(['chart', '--output', str(self.output)])

    def live_data(self):
        text = (self.output / 'usage-live-data.js').read_text()
        prefix = 'globalThis.asiLiveData?.('
        self.assertTrue(text.startswith(prefix) and text.endswith(');'))
        revision, packed = json.loads('[' + text[len(prefix):-2] + ']')
        return revision, packed

    def snapshot(self):
        return synthetic(30, 300)

    def test_large_live_data_goes_in_parts_and_the_commit_marker_is_unchanged(self):
        with patch.dict(os.environ, {'ASI_SNAPSHOT_PART_CHARS': '8000'}):
            result = app.publish_shared_usage(self.snapshot(), self.args, '1'.zfill(20))
        revision, packed = self.live_data()
        self.assertEqual(revision, result['revision'])
        self.assertEqual(packed['encoding'], 'gzip-base64-parts')
        texts = part_texts(packed)
        self.assertGreater(len(texts), 10)
        self.assertTrue(all(len(t) <= 8000 for t in texts))
        state = json.loads((self.output / 'usage-state.json').read_text())
        self.assertEqual(unpack(packed), state['snapshot'])
        self.assertEqual(state['snapshot']['event_previews']['Claude:omitted'], None)
        # The menu bar app and Python readers follow usage-live.js, which keeps its form.
        commit = app.read_shared_commit(self.output)
        self.assertEqual(commit['revision'], revision)
        report = json.loads(base64.b64decode(commit['report_base64']))
        self.assertEqual(report['sync_revision'], revision)
        self.assertEqual(app.read_shared_usage(self.output)['revision'], revision)

    def test_small_live_data_keeps_the_single_blob(self):
        app.publish_shared_usage(self.snapshot(), self.args, '1'.zfill(20))
        _, packed = self.live_data()
        self.assertEqual(packed['encoding'], 'gzip-base64')
        self.assertEqual(unpack(packed), json.loads((self.output / 'usage-state.json').read_text())['snapshot'])


class PreviewBudgetTests(unittest.TestCase):
    def previews(self):
        # s9 is the newest session; undated events sort a session last.
        sessions = {'Codex:s%d' % n: [dict(kind='usage', ts=1000.0 * n + k, model='m') for k in range(3)] for n in range(10)}
        sessions['Codex:undated'] = [dict(kind='usage', ts=None)]
        return sessions

    def test_newest_sessions_keep_previews_until_the_budget_is_reached(self):
        previews = self.previews()
        entry = lambda sid: len(json.dumps({sid: previews[sid]}, separators=(',', ':'))) - 2
        budget = 2 + entry('Codex:s9') + 1 + entry('Codex:s8') + 1 + entry('Codex:s7') + 5
        kept, limit = app.bound_event_previews(previews, budget)
        self.assertEqual(set(kept), set(previews))
        self.assertEqual([sid for sid, items in kept.items() if items is not None], ['Codex:s9', 'Codex:s8', 'Codex:s7'])
        self.assertEqual(kept['Codex:s9'], previews['Codex:s9'])
        self.assertIsNone(kept['Codex:undated'])
        self.assertEqual(limit, dict(budget_bytes=budget, sessions_with_previews=3, sessions_without_previews=8))
        stored = {sid: items for sid, items in kept.items() if items is not None}
        self.assertLessEqual(len(json.dumps(stored, separators=(',', ':'))), budget)
        everything, limit = app.bound_event_previews(previews, 10 ** 9)
        self.assertEqual(everything, previews)
        self.assertEqual(limit['sessions_without_previews'], 0)
        nothing, limit = app.bound_event_previews(previews, 10)
        self.assertTrue(all(items is None for items in nothing.values()))
        self.assertEqual(limit['sessions_with_previews'], 0)

    def test_budget_setting_and_fallbacks(self):
        clean = {k: v for k, v in os.environ.items() if not k.endswith('PREVIEW_BUDGET_MB')}
        with patch.dict(os.environ, clean, clear=True):
            self.assertEqual(app.preview_budget_bytes(), 64_000_000)
            for value, expected in (('0.5', 500_000), ('128', 128_000_000), ('0', 64_000_000), ('-3', 64_000_000),
                                    ('abc', 64_000_000), ('nan', 64_000_000), ('inf', 64_000_000), ('', 64_000_000),
                                    ('1e305', 10 ** 15), ('1e-9', 64_000_000)):
                with self.subTest(value=value), patch.dict(os.environ, {'ASI_PREVIEW_BUDGET_MB': value}):
                    self.assertEqual(app.preview_budget_bytes(), expected)
            with patch.dict(os.environ, {'AISAD_PREVIEW_BUDGET_MB': '2'}):
                self.assertEqual(app.preview_budget_bytes(), 2_000_000)

    def test_dashboard_snapshot_records_the_limit_and_keeps_usage_complete(self):
        from test_evidence import EvidenceTests
        fixture = EvidenceTests()
        fixture.setUp()
        try:
            fixture.write('.codex/sessions/newer.jsonl', fixture.trace('newer'))
            older = [dict(event, timestamp=event['timestamp'].replace('2026-09-07', '2026-09-06')) for event in fixture.trace('older')]
            fixture.write('.codex/sessions/older.jsonl', older)
            clean = {k: v for k, v in os.environ.items() if not k.endswith('PREVIEW_BUDGET_MB')}
            with patch.dict(os.environ, clean, clear=True):
                full = app.make_snapshot(fixture.args('--all-time'), dashboard=True)
                size = len(json.dumps({'Codex:newer': full['event_previews']['Codex:newer']}, separators=(',', ':')))
                # Room for the newest session only: the older one is about as large again.
                with patch.dict(os.environ, {'ASI_PREVIEW_BUDGET_MB': str((size + 50) / 1_000_000)}):
                    budget = app.preview_budget_bytes()
                    bounded = app.make_snapshot(fixture.args('--all-time'), dashboard=True)
                page = embedded((fixture.output / 'dashboard.html').read_text())
        finally:
            fixture.doCleanups()
        self.assertEqual(full['event_preview_limit']['sessions_without_previews'], 0)
        self.assertEqual(bounded['event_previews']['Codex:newer'], full['event_previews']['Codex:newer'])
        self.assertIsNone(bounded['event_previews']['Codex:older'])
        self.assertGreaterEqual(budget, size)
        self.assertEqual(bounded['event_preview_limit'], dict(budget_bytes=budget, sessions_with_previews=1, sessions_without_previews=1))
        page = unpack(page)
        self.assertEqual(page['event_preview_limit'], bounded['event_preview_limit'])
        self.assertIsNone(page['event_previews']['Codex:older'])
        for key in ('rows', 'request_stats', 'session_details', 'model_fit', 'summary'):
            self.assertEqual(bounded[key], full[key], key)


if __name__ == '__main__':
    unittest.main()
