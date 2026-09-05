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
const payments = [
  { date: '2026-03-05', provider: 'Codex', model: 'gpt-5.6-sol', project: 'api', amount: 20 },
  { date: '2026-03-06', provider: 'Claude', model: 'claude-opus-5', project: 'web', amount: 10 },
  { date: '2026-03-01', provider: 'Codex', model: 'gpt-5.6-sol', project: 'api', amount: 10 },
  { date: '2026-03-01', provider: 'Claude', model: 'claude-opus-5', project: 'web', amount: 10 },
];

(async () => {
  const html = await readFile(path.join(__dirname, '../output/demo/dashboard.html'), 'utf8');
  const pattern = /(<script id="snapshot" type="application\/json">)([\s\S]*?)(<\/script>)/;
  const template = JSON.parse(html.match(pattern)[2]);
  const browser = await chromium.launch({ headless: true });
  let passed = 0;
  const errors = [], network = [];
  const values = page => page.locator('#cards .value').allTextContents();
  const delta = (page, index) => page.locator('#cards .card').nth(index).locator('.delta').textContent();
  async function check(name, overrides, run) {
    const data = { ...template, as_of_date: '2026-03-10', generated: '2026-03-11T00:30:00Z',
      timezone: 'America/Los_Angeles', rows: structuredClone(rows), billing: structuredClone(payments),
      billing_loaded: true, ...overrides };
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
      assert.deepEqual(await values(page), ['$7.00', '4.3K', '5', '2', '72.9%', '$30.00']);
      assert.equal(await delta(page, 0), '+16.7% · prev $6.00');
      assert.equal(await delta(page, 2), '+150.0% · prev 2');
      assert.equal(await delta(page, 3), '0.0% · prev 2');
      assert.equal(await delta(page, 4), '+35.4 pp · prev 37.5%');
      assert.equal(await delta(page, 5), '+50.0% · prev $20.00');
      assert.match(await page.locator('#comparison-note').textContent(), /2026-02-25 – 2026-03-03/);
      assert.equal(await page.locator('#daily rect[data-series="previous"]').count(), 2);
      assert.match(await page.locator('#daily').textContent(), /previous · 2026-02-25/);
      assert.equal(await page.evaluate(() => shiftDate('2024-03-01', -1)), '2024-02-29');
    });
    await check('provider grouping and click filter apply to both periods', {}, async page => {
      assert.equal(await page.locator('#providers-table [data-provider]').count(), 2);
      await page.locator('[data-provider="Codex"]').click();
      assert.equal(await page.locator('#provider').inputValue(), 'Codex');
      assert.deepEqual(await values(page), ['$3.00', '1.8K', '3', '1', '50.0%', '$20.00']);
      assert.equal(await delta(page, 0), '+50.0% · prev $2.00');
      assert.equal(await page.locator('#providers-table [data-provider]').count(), 1);
      await page.click('#reset');
      assert.equal(await page.locator('#provider').inputValue(), '');
      assert.equal((await values(page))[0], '$7.00');
    });
    await check('model/project/role filters; role does not reallocate payments', {}, async page => {
      await page.selectOption('#role', 'subagent');
      assert.equal((await values(page))[0], '$4.00');
      assert.equal((await values(page))[5], '$30.00');
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
      assert.equal(await delta(page, 2), '+150.0% · prev 2');
    });
    await check('cache TTL price ranges suppress false precision', { rows: rows.map(r => r.date === '2026-03-04' ? { ...r, cost_high: 2 } : r) }, async page => {
      assert.equal(await delta(page, 0), 'Incomplete pricing · no delta');
    });
    await check('zero cost baseline never produces Infinity', { rows: rows.map(r => r.date < '2026-03-04' ? { ...r, cost: 0, cost_high: 0 } : r) }, async page => {
      assert.equal(await delta(page, 0), 'No nonzero baseline · prev $0.00');
      assert(!/Infinity|NaN/.test(await page.locator('body').textContent()));
    });
    await check('empty history and invalid date range are explicit', { rows: [], billing: [], billing_loaded: false }, async page => {
      assert.equal((await values(page))[2], '0');
      assert.equal(await delta(page, 0), 'No previous-period data');
      await page.fill('#from', '2026-03-12'); await page.locator('#from').dispatchEvent('change');
      assert.match(await page.locator('#comparison-note').textContent(), /Choose a valid date range/);
      assert.equal(await page.locator('#daily svg').count(), 0);
    });
    assert.deepEqual(errors, []);
    assert.deepEqual(network, []);
    console.log(`${passed} dashboard regression scenarios passed; no browser errors or network requests.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
