// Browser regression checks with synthetic data only. Requires Playwright/Chromium.
const assert = require('node:assert/strict');
const { readFile } = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');

const row = (provider, date, session, input, cached, output, cost, requests, role = 'main') => ({
  provider, date, session, input, cached, output, cost, cost_high: cost, requests, role,
  model: provider === 'Codex' ? 'gpt-5.6-sol' : 'claude-opus-5',
  project: provider === 'Codex' ? 'api' : 'web', total: input + output,
  write: 0, unpriced: 0, write_unknown: 0, assumed: 0, max_context: input,
  parts: [cost, 0, 0, 0, 0],
});
const rows = [
  row('Codex', '2026-03-04', 'shared', 1000, 500, 200, 1, 2),
  row('Codex', '2026-03-10', 'shared', 500, 250, 100, 2, 1),
  row('Codex', '2026-03-03', 'shared', 1000, 250, 100, 2, 1),
  row('Claude', '2026-03-06', 'claude-current', 2000, 1800, 500, 4, 2, 'subagent'),
  row('Claude', '2026-02-25', 'claude-previous', 1000, 500, 100, 4, 1, 'subagent'),
  row('Codex', '2026-02-24', 'too-old', 10000, 0, 0, 99, 99),
  row('Codex', '2026-03-11', 'future', 10000, 0, 0, 99, 99),
];
(async () => {
  const html = await readFile(path.join(__dirname, '../output/demo/dashboard.html'), 'utf8');
  const pattern = /(<script id="snapshot" type="application\/json">)([\s\S]*?)(<\/script>)/;
  const template = JSON.parse(html.match(pattern)[2]);
  const expected = JSON.parse(await readFile(path.join(__dirname, '../output/demo/expected-analysis.json'), 'utf8'));
  const browser = await chromium.launch({ headless: true });
  let passed = 0;
  const errors = [], network = [];
  const values = page => page.locator('#cards .value').allTextContents();
  const delta = (page, index) => page.locator('#cards .card').nth(index).locator('.delta').textContent();
  async function check(name, overrides, run) {
    const data = { ...template, as_of_date: '2026-03-10', generated: '2026-03-11T00:30:00Z',
      timezone: 'America/Los_Angeles', rows: structuredClone(rows), analysis: {...template.analysis, records: []}, ...overrides };
    const json = JSON.stringify(data).replace(/</g, '\\u003c');
    const page = await browser.newPage({ locale: 'en-US', timezoneId: 'Pacific/Auckland' });
    page.on('pageerror', e => errors.push(String(e)));
    page.on('request', r => network.push(r.url()));
    try {
      await page.setContent(html.replace(pattern, (_, start, unused, end) => start + json + end));
      await run(page);
      passed++;
      console.log('PASS ' + name);
    } finally { await page.close(); }
  }
  try {
    await check('calendar week, boundaries, weighted cache and distinct sessions', {}, async page => {
      assert.equal(await page.locator('#from').inputValue(), '2026-03-04');
      assert.equal(await page.locator('#to').inputValue(), '2026-03-10');
      assert.deepEqual(await values(page), ['$7.00', '2', '72.9%', '$7.00', '—']);
      assert.equal(await delta(page, 0), '+16.7% · prev $6.00');
      assert.equal(await page.locator('#requests-delta').textContent(), 'Requests: +150.0% · prev 2');
      assert.equal(await delta(page, 1), '0.0% · prev 2');
      assert.equal(await delta(page, 2), '+35.4 pp · prev 37.5%');
      assert.match(await page.locator('#comparison-note').textContent(), /2026-02-25 – 2026-03-03/);
      assert.equal(await page.locator('#daily rect[data-series="previous"]').count(), 2);
      assert.match(await page.locator('#daily').textContent(), /previous · 2026-02-25/);
      assert.equal(await page.evaluate(() => shiftDate('2024-03-01', -1)), '2024-02-29');
    });
    await check('provider grouping and click filter apply to both periods', {}, async page => {
      assert.equal(await page.locator('#providers-table [data-provider]').count(), 2);
      await page.locator('[data-provider="Codex"]').click();
      assert.equal(await page.locator('#provider').inputValue(), 'Codex');
      assert.deepEqual(await values(page), ['$3.00', '1', '50.0%', '$3.00', '—']);
      assert.equal(await delta(page, 0), '+50.0% · prev $2.00');
      assert.equal(await page.locator('#providers-table [data-provider]').count(), 1);
      await page.click('#reset');
      assert.equal(await page.locator('#provider').inputValue(), '');
      assert.equal((await values(page))[0], '$7.00');
    });
    await check('model/project/role filters apply to both periods', {}, async page => {
      await page.selectOption('#role', 'subagent');
      assert.equal((await values(page))[0], '$4.00');
      assert.equal(await delta(page, 0), '0.0% · prev $4.00');
      await page.click('#reset');
      await page.selectOption('#model', 'gpt-5.6-sol');
      await page.selectOption('#project', 'api');
      assert.equal((await values(page))[0], '$3.00');
      assert.equal(await delta(page, 0), '+50.0% · prev $2.00');
    });
    await check('all-time, custom equal-length comparison and reset', {}, async page => {
      await page.selectOption('#period', 'all');
      assert.equal((await values(page))[0], '$211.00');
      assert.equal(await page.locator('#cards .delta').count(), 0);
      assert.equal(await page.locator('#daily rect[data-series="previous"]').count(), 0);
      await page.fill('#from', '2026-03-04'); await page.locator('#from').dispatchEvent('change');
      await page.fill('#to', '2026-03-06'); await page.locator('#to').dispatchEvent('change');
      assert.equal(await page.locator('#period').inputValue(), 'custom');
      assert.match(await page.locator('#comparison-note').textContent(), /2026-03-01 – 2026-03-03/);
      assert.equal((await values(page))[0], '$5.00');
      await page.click('#reset');
      assert.equal(await page.locator('#period').inputValue(), '7');
      assert.equal((await values(page))[0], '$7.00');
    });
    await check('missing history is not a zero baseline', { rows: rows.filter(r => r.date >= '2026-03-04') }, async page => {
      assert.equal(await delta(page, 0), 'No previous-period data');
      assert.equal(await page.locator('#daily rect[data-series="previous"]').count(), 0);
    });
    await check('provider-specific missing history is not borrowed from another provider', { rows: rows.filter(r => r.provider === 'Codex' || r.date >= '2026-03-04') }, async page => {
      await page.selectOption('#provider', 'Claude');
      assert.equal(await delta(page, 0), 'No previous-period data');
    });
    await check('no current observations retain prior bars without a -100% claim', { rows: rows.filter(r => r.date < '2026-03-04') }, async page => {
      assert.equal((await values(page))[0], '—');
      assert.equal(await delta(page, 0), 'No current-period data');
      assert.equal(await page.locator('#daily rect[data-series="current"]').count(), 0);
      assert.equal(await page.locator('#daily rect[data-series="previous"]').count(), 2);
    });
    await check('unknown prices suppress cost delta but retain token comparisons', { rows: rows.map(r => r.date === '2026-03-03' ? { ...r, unpriced: r.requests, cost: 0, cost_high: 0 } : r) }, async page => {
      assert.equal(await delta(page, 0), 'Incomplete pricing · no delta');
      assert.equal(await page.locator('#requests-delta').textContent(), 'Requests: +150.0% · prev 2');
    });
    await check('cache TTL price ranges suppress false precision', { rows: rows.map(r => r.date === '2026-03-04' ? { ...r, cost_high: 2 } : r) }, async page => {
      assert.equal(await delta(page, 0), 'Incomplete pricing · no delta');
    });
    await check('zero cost baseline never produces Infinity', { rows: rows.map(r => r.date < '2026-03-04' ? { ...r, cost: 0, cost_high: 0 } : r) }, async page => {
      assert.equal(await delta(page, 0), 'No nonzero baseline · prev $0.00');
      assert(!/Infinity|NaN/.test(await page.locator('body').textContent()));
    });
    await check('empty history and invalid date range are explicit', { rows: [] }, async page => {
      assert.equal(await page.locator('#requests-value').textContent(), '0');
      assert.equal(await delta(page, 0), 'No previous-period data');
      await page.fill('#from', '2026-03-12'); await page.locator('#from').dispatchEvent('change');
      assert.match(await page.locator('#comparison-note').textContent(), /Choose a valid date range/);
      assert.equal(await page.locator('#daily svg').count(), 0);
    });
    await check('browser diagnostics reconcile with Python, including filter scope', template, async page => {
      const diagnostic = await page.evaluate(() => diagnostics(selectedRecords()));
      const oracle = expected.current.diagnostics;
      assert.equal(diagnostic.findings.length, oracle.finding_count);
      assert.equal(diagnostic.flagged, oracle.flagged_sessions);
      assert.equal(diagnostic.traceRecords, oracle.trace_records);
      assert(Math.abs(diagnostic.scenario - oracle.scenario_savings_usd) < 1e-9);
      assert(Math.abs(diagnostic.scenarioHigh - oracle.scenario_savings_high_usd) < 1e-9);
      for (const finding of diagnostic.findings) {
        const match = oracle.findings.find(f => f.rule === finding.rule && f.session === finding.session && f.model === finding.model && f.project === finding.project && f.role === finding.role && f.pool === finding.pool);
        assert(match);
        assert.equal(finding.requests, match.requests);
        assert.equal(finding.unpriced, match.unpriced_requests);
        assert(Math.abs(finding.cost - match.known_cost_usd) < 1e-9);
        assert.deepEqual(finding.evidence, match.evidence);
        if (match.savings_usd == null) assert.equal(finding.savings, null);
        else assert(Math.abs(finding.savings - match.savings_usd) < 1e-9);
      }
      assert.deepEqual(new Set(diagnostic.findings.map(f => f.rule)), new Set(Object.keys(template.analysis.rules)));
      const poolText = await page.locator('#pools').textContent();
      await page.selectOption('#provider', 'Claude');
      assert.equal(await page.locator('#pools').textContent(), poolText);
      assert((await page.evaluate(() => diagnostics(selectedRecords()).findings)).every(f => f.session.startsWith('Claude:')));
      await page.click('#reset');
      await page.selectOption('#pool', 'managed');
      assert.equal(await page.locator('#card-sessions .value').textContent(), '1');
      assert.equal(await page.locator('#pools').textContent(), poolText);
    });
    await check('recommendations, session drilldown, context, cache, keyboard and dark theme', template, async page => {
      await page.click('#tab-recommendations');
      await page.selectOption('#check-filter', 'large_tool_result');
      assert.equal(await page.locator('#findings .finding').count(), 1);
      assert.match(await page.locator('#findings').textContent(), /46.0 KB/);
      assert.match(await page.locator('#findings').textContent(), /Not estimated/);
      await page.locator('#findings [data-session]').click();
      assert.equal(await page.locator('#session-dialog').evaluate(el => el.open), true);
      assert.equal(await page.locator('#session-title').textContent(), 'Codex:large-tool-result');
      assert.equal(await page.locator('#session-timeline circle').count(), 3);
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#session-dialog').evaluate(el => el.open), false);
      await page.click('#tab-context');
      assert(await page.locator('#tool-coverage').isVisible());
      await page.click('#tab-cache');
      assert.equal(await page.locator('#cache-findings .finding').count(), 1);
      await page.locator('#tab-cache').press('Home');
      assert.equal(await page.locator('#tab-overview').getAttribute('aria-selected'), 'true');
      await page.click('#theme');
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
      await page.setViewportSize({width:390, height:844});
      for (const view of ['overview', 'recommendations', 'sessions', 'context', 'cache']) {
        await page.click('#tab-' + view);
        assert(await page.locator('#view-' + view).isVisible());
        assert(!(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)), view + ' overflows');
      }
    });
    assert.deepEqual(errors, []);
    assert.deepEqual(network, []);
    console.log(`${passed} dashboard regression scenarios passed; no browser errors or network requests.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
