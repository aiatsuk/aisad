"""Hand-computed monetary regressions for the current offline fallback catalog."""
import collections
import json
from pathlib import Path
import tempfile
import unittest
import agent_usage as app


class CostAccuracyTests(unittest.TestCase):
    def price(self, model, provider="Codex", tier="standard", **usage):
        row = dict(model=model, provider=provider, ts=app.timestamp("2026-10-22"),
                   tier=tier, speed="unknown", geo="global", **app.normalize_usage(usage, provider))
        return app.price_request(row, app.default_prices())

    def test_gpt61_modes_keep_caching_and_output_separate(self):
        for mode, multiplier in [("standard", 1), ("priority", 2), ("flex", .5),
                                 ("batch", .5), ("ultrafast", 6)]:
            result = self.price("gpt-6.1-sol", tier=mode, input_tokens=100000,
                                cached_input_tokens=80000, output_tokens=10000)
            self.assertAlmostEqual(result["cost"], .148 * multiplier, places=12)

    def test_gpt61_long_context_applies_input_and_output_multipliers(self):
        result = self.price("gpt-6.1-sol", input_tokens=1000000,
                            cached_input_tokens=800000, output_tokens=10000)
        self.assertAlmostEqual(result["cost"], 1.11, places=12)

    def test_sonnet55_cache_reads_writes_and_output(self):
        result = self.price("claude-sonnet-5-5", "Claude", input_tokens=100,
                            cache_read_input_tokens=1000, cache_creation_input_tokens=50,
                            cache_creation={"ephemeral_5m_input_tokens": 50}, output_tokens=20)
        self.assertAlmostEqual(result["cost"], .000625, places=12)

    def test_haiku55_context_tier_boundary(self):
        low = self.price("claude-haiku-5-5", "Claude", input_tokens=99999, output_tokens=100)
        high = self.price("claude-haiku-5-5", "Claude", input_tokens=100001, output_tokens=100)
        self.assertAlmostEqual(low["cost"], .0100499, places=12)
        self.assertAlmostEqual(high["cost"], .0502505, places=12)

    def test_partial_grok_cost_is_a_known_subtotal(self):
        row = dict(timestamp=1792634400, params=dict(sessionId="one", update=dict(
            sessionUpdate="turn_completed", prompt_id="a", usage=dict(
                inputTokens=100, outputTokens=20, costUsdTicks=1234567890, costIsPartial=True))))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/".grok/sessions/project/one/updates.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(row))
            records = app.grok_usage(app.parser().parse_args(["--home", directory]), collections.Counter())
        total = app.grok_totals(records)
        self.assertEqual(total["incomplete_turns"], 1)
        self.assertAlmostEqual(total["known_reported_cost_usd"], .123456789)
        self.assertFalse(total["included_in_api_estimate"])


if __name__ == "__main__":
    unittest.main()
