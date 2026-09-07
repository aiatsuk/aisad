"""Recorded processing tiers affect prices, never token counts."""
import json
from pathlib import Path
import tempfile
import unittest

import agent_usage as app


class RecordedTierTests(unittest.TestCase):
    def test_settings_changes_apply_only_to_subsequent_usage(self):
        records=[dict(type='session_meta',payload=dict(id='one')),
                 dict(type='turn_context',payload=dict(model='gpt-5.6-sol'))]
        counter=0
        def usage():
            nonlocal counter
            counter+=1
            records.append(dict(type='event_msg',timestamp=f'2026-09-01T01:00:{counter:02d}Z',
                payload=dict(type='token_count',info=dict(
                    last_token_usage=dict(input_tokens=1000,cached_input_tokens=800,cache_write_input_tokens=100,output_tokens=50,reasoning_output_tokens=30),
                    total_token_usage=dict(input_tokens=1000*counter,output_tokens=50*counter,total_tokens=1050*counter)))))
        def settings(value):
            records.append(dict(type='event_msg',payload=dict(type='thread_settings_applied',thread_settings=value)))
        usage() # Unmarked history must not borrow the later Fast tier.
        settings({'service_tier':'priority'});usage()
        settings({'unrelated':'value'});usage()
        settings({'service_tier':'default'});usage()
        settings({'service_tier':'future-mode'});usage()
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'trace.jsonl'
            source.write_text(''.join(json.dumps(r)+'\n' for r in records))
            parsed=app.parse_codex(source)
        rows=parsed['requests']
        self.assertEqual([r['tier'] for r in rows],['unknown','priority','priority','default','future-mode'])
        prices=[app.price_request(r,app.default_prices()) for r in rows]
        self.assertAlmostEqual(prices[1]['cost'],2*prices[0]['cost'])
        self.assertAlmostEqual(prices[2]['cost'],prices[1]['cost'])
        self.assertAlmostEqual(prices[3]['cost'],prices[0]['cost'])
        self.assertIn('Standard tier assumed',prices[0]['assumptions'])
        self.assertNotIn('Standard tier assumed',prices[3]['assumptions'])
        self.assertIsNone(prices[4]['cost'])
        self.assertEqual(prices[4]['price_status'],'unknown_tier')
        self.assertEqual(sum(r['input']+r['output'] for r in rows),5250)
        self.assertTrue(all(r['input']==r['uncached']+r['cached']+r['write'] for r in rows))
        self.assertEqual(parsed['quality']['codex_recorded_tier_events'],3)
        self.assertEqual(len([e for e in parsed['events'] if e['kind']=='settings']),4)

    def test_cross_provider_buckets_and_reasoning_are_counted_once(self):
        claude=app.normalize_usage(dict(input_tokens=100,cache_read_input_tokens=800,
            cache_creation_input_tokens=100,cache_creation={'ephemeral_5m_input_tokens':100},output_tokens=50),'Claude')
        codex=app.normalize_usage(dict(input_tokens=1000,cached_input_tokens=800,
            cache_write_input_tokens=100,output_tokens=50,reasoning_output_tokens=30),'Codex')
        for row in [claude,codex]:
            self.assertEqual((row['input'],row['uncached'],row['cached'],row['write'],row['output'],row['total']),
                             (1000,100,800,100,50,1050))
        self.assertEqual(sum(r['total'] for r in [claude,codex]),2100)


if __name__=='__main__':unittest.main()
