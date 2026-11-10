// Browser regression checks with synthetic data only. Requires Playwright/Chromium.
const assert = require('node:assert/strict');
const { readFile } = require('node:fs/promises');
const path = require('node:path');
const zlib = require('node:zlib');
const { chromium } = require('playwright');

function readSnapshot(raw) {
  // Large demos embed gzip-base64. Overrides must apply to the decoded snapshot.
  const data = JSON.parse(raw);
  if (data.encoding !== 'gzip-base64') return data;
  return JSON.parse(zlib.gunzipSync(Buffer.from(data.data, 'base64')).toString('utf8'));
}

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
  // Expose lexical helpers only in the synthetic test document, never in shipped HTML.
  const html = (await readFile(path.join(__dirname, '../output/demo/dashboard.html'), 'utf8')).replace(
    '})().catch(error=>{',
    'Object.assign(window,{shiftDate,telemetry,selectedRecords,aggregate,D,chosen,applyLiveSnapshot});\n})().catch(error=>{');
  const pattern = /(<script id="snapshot" type="application\/json">)([\s\S]*?)(<\/script>)/;
  const template = readSnapshot(html.match(pattern)[2]);
  const expected = JSON.parse(await readFile(path.join(__dirname, '../output/demo/expected-usage.json'), 'utf8'));
  const browser = await chromium.launch({ headless: true });
  let passed = 0;
  const errors = [], network = [];
  const values = page => page.locator('#cards .value').allTextContents();
  const delta = (page, index) => page.locator('#cards .card').nth(index).locator('.delta').textContent();
  async function check(name, overrides, run) {
    const data = { ...template, as_of_date: '2026-03-10', generated: '2026-03-11T00:30:00Z',
      timezone: 'America/Los_Angeles', rows: structuredClone(rows), request_stats: [], ...overrides };
    const json = JSON.stringify(data).replace(/</g, '\\u003c');
    const page = await browser.newPage({ locale: 'en-US', timezoneId: 'Pacific/Auckland' });
    page.on('pageerror', e => errors.push(String(e)));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    page.on('request', r => network.push(r.url()));
    try {
      await page.setContent(html.replace(pattern, (_, start, unused, end) => start + json + end));
      await page.waitForSelector('#interactive-dashboard', {state: 'visible'});
      await run(page);
      passed++;
      console.log('PASS ' + name);
    } finally { await page.close(); }
  }
  try {
    await check('calendar week, boundaries, weighted cache and distinct sessions', {}, async page => {
      assert.equal(await page.locator('#from').inputValue(), '2026-03-04');
      assert.equal(await page.locator('#to').inputValue(), '2026-03-10');
      assert.deepEqual(await values(page), ['$7.00', '2', '72.9%', '$7.00']);
      assert.equal(await delta(page, 0), '+16.7% · prev $6.00');
      assert.equal(await page.locator('#requests-delta').textContent(), 'Requests: +150.0% · prev 2');
      assert.equal(await delta(page, 1), '0.0% · prev 2');
      assert.equal(await delta(page, 2), '+35.4 pp · prev 37.5%');
      assert.match(await page.locator('#comparison-note').textContent(), /Feb 25 – Mar 3/);
      assert.equal(await page.locator('#daily rect[data-series="previous"]').count(), 2);
      assert.match(await page.locator('#daily').textContent(), /previous · 2026-02-25/);
      assert.equal(await page.evaluate(() => shiftDate('2024-03-01', -1)), '2024-02-29');
    });
    await check('provider grouping and click filter apply to both periods', {}, async page => {
      assert.equal(await page.locator('#providers-table [data-provider]').count(), 2);
      await page.locator('[data-provider="Codex"]').click();
      assert.equal(await page.locator('#provider').inputValue(), 'Codex');
      assert.deepEqual(await values(page), ['$3.00', '1', '50.0%', '$3.00']);
      assert.equal(await delta(page, 0), '+50.0% · prev $2.00');
      assert.equal(await page.locator('#providers-table [data-provider]').count(), 1);
      await page.click('#reset');
      assert.equal(await page.locator('#provider').inputValue(), '');
      assert.equal((await values(page))[0], '$7.00');
    });
    await check('model/project/role filters apply to both periods', {}, async page => {
      await page.click('#filter-toggle');
      await page.selectOption('#role', 'subagent');
      assert.equal((await values(page))[0], '$4.00');
      assert.equal(await delta(page, 0), '0.0% · prev $4.00');
      await page.click('#reset');
      await page.click('#filter-toggle');
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
      await page.selectOption('#period', 'custom');
      await page.fill('#from', '2026-03-04'); await page.locator('#from').dispatchEvent('change');
      await page.fill('#to', '2026-03-06'); await page.locator('#to').dispatchEvent('change');
      assert.equal(await page.locator('#period').inputValue(), 'custom');
      assert.match(await page.locator('#comparison-note').textContent(), /Mar 1 – Mar 3/);
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
    await check('unknown prices suppress cost delta and retain request comparisons', { rows: rows.map(r => r.date === '2026-03-03' ? { ...r, unpriced: r.requests, cost: 0, cost_high: 0 } : r) }, async page => {
      assert.equal(await delta(page, 0), 'Incomplete pricing · no delta');
      assert.equal(await page.locator('#requests-delta').textContent(), 'Requests: +150.0% · prev 2');
    });
    await check('cache TTL price ranges suppress false precision', { rows: rows.map(r => r.date === '2026-03-04' ? { ...r, cost_high: 2 } : r) }, async page => {
      assert.equal(await delta(page, 0), 'Price range · no delta');
    });
    await check('cache token and cost components reconcile and follow provider filters', { rows: [
      {...row('Claude','2026-03-10','cache-claude',1000,600,50,10,1),write:100,write_unknown:100,cost:10.5,cost_high:11.5,parts:[1,2,3,4,.5]},
      {...row('Codex','2026-03-10','cache-codex',500,250,100,5,1),parts:[1,1,0,3,0]},
    ] }, async page => {
      assert.equal(await page.locator('#pools').count(), 0);
      assert.deepEqual(await page.locator('#token-cards .value').allTextContents(), ['550','850','100','150']);
      assert.match(await page.locator('#search-cost').textContent(), /Web search: \$0.50/);
      assert.match(await page.locator('[data-component="cache_writes"] .component-cost').textContent(), /\$3.00–\$4.00/);
      assert.match(await page.locator('#parts').textContent(), /\$3.00–\$4.00/);
      await page.selectOption('#provider','Claude');
      assert.deepEqual(await page.locator('#token-cards .value').allTextContents(), ['300','600','100','50']);
      await page.click('#tab-cache');
      assert.deepEqual(await page.locator('#cache-table tbody td').allTextContents(), ['claude-opus-5','1,000','300','600','100','60.0%','$1.00','$2.00','$3.00–$4.00']);
      await page.selectOption('#provider','Codex');
      assert.match(await page.locator('#cache-table tbody').textContent(), /\$0.00/);
      assert.equal(await page.locator('#search-cost').isHidden(), true);
    });
    await check('zero cost baseline never produces Infinity', { rows: rows.map(r => r.date < '2026-03-04' ? { ...r, cost: 0, cost_high: 0 } : r) }, async page => {
      assert.equal(await delta(page, 0), 'No nonzero baseline · prev $0.00');
      assert(!/Infinity|NaN/.test(await page.locator('body').textContent()));
    });
    await check('empty history and invalid date range are explicit', { rows: [] }, async page => {
      assert.equal(await page.locator('#requests-value').textContent(), '0');
      assert.equal(await delta(page, 0), 'No previous-period data');
      await page.selectOption('#period', 'custom');
      await page.fill('#from', '2026-03-12'); await page.locator('#from').dispatchEvent('change');
      assert.match(await page.locator('#comparison-note').textContent(), /Choose a valid date range/);
      assert.equal(await page.locator('#daily svg').count(), 0);
    });
    await check('browser statistics reconcile with Python and retain filter scope', template, async page => {
      assert.equal(expected.schema_version, 2);
      assert(!('analysis' in template));
      assert(!('analysis_rules' in expected));
      const measured = await page.evaluate(() => telemetry(selectedRecords()));
      const oracle = expected.current.telemetry;
      assert.equal(measured.traceRecords, oracle.trace_records);
      assert.equal(measured.totalRecords, oracle.total_records);
      assert.deepEqual(measured.stats, oracle.tool_stats);
      const totals = await page.evaluate(() => aggregate(D.rows.filter(r => chosen(r))));
      assert.equal(totals.requests, expected.current.totals.requests);
      assert.equal(totals.input, expected.current.totals.input_tokens);
      assert.equal(totals.output, expected.current.totals.output_tokens);
      assert(Math.abs(totals.cost - expected.current.totals.known_cost_usd) < 1e-9);
      assert.equal(await page.locator('#pools').count(), 0);
      await page.selectOption('#provider', 'Claude');
      assert.equal(await page.locator('#token-cards .card').count(), 4);
      assert((await page.evaluate(() => selectedRecords())).every(r => r.session.startsWith('Claude:')));
      assert.equal(await page.evaluate(() => telemetry(selectedRecords()).totalRecords), expected.current.by_provider.find(p => p.name === 'Claude').requests);
      await page.click('#reset');
      await page.click('#filter-toggle');
      await page.selectOption('#pool', 'managed');
      assert.equal(await page.locator('#card-sessions .value').textContent(), '1');
      assert.equal(await page.locator('#token-cards .card').count(), 4);
    });
    await check('statistics-only views, session drilldown, keyboard and dark theme', template, async page => {
      assert.equal(await page.locator('[data-tab]').count(), 5);
      assert.equal(await page.locator('#card-savings, #view-recommendations, #review-next').count(), 0);
      await page.click('#tab-sessions');
      await page.fill('#search', 'large-tool-result');
      await page.locator('#sessions-table [data-session]').click();
      assert.equal(await page.locator('#session-dialog').evaluate(el => el.open), true);
      assert.equal(await page.locator('#session-title').textContent(), 'Codex:large-tool-result');
      assert.equal(await page.locator('#session-timeline circle').count(), 3);
      assert.equal(await page.locator('#session-findings').count(), 0);
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#session-dialog').evaluate(el => el.open), false);
      await page.click('#tab-context');
      assert(await page.locator('#tool-coverage').isVisible());
      assert.match(await page.locator('#context-cards').textContent(), /46.0 KB/);
      await page.click('#tab-cache');
      assert.match(await page.locator('#cache-cards').textContent(), /Cache writes/);
      assert.equal(await page.locator('#cache-findings').count(), 0);
      await page.locator('#tab-cache').press('Home');
      assert.equal(await page.locator('#tab-overview').getAttribute('aria-selected'), 'true');
      await page.click('#theme');
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
      await page.setViewportSize({width:390, height:844});
      for (const view of ['overview', 'sessions', 'context', 'cache', 'fit']) {
        await page.click('#tab-' + view);
        assert(await page.locator('#view-' + view).isVisible());
        assert(!(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)), view + ' overflows');
        // The statistics views stay free of advice; Model fit is the one view that compares with the guide.
        if (view !== 'fit') assert(!/recommendations|scenario savings|review next|possible rebuilds|flagged|benchmark/i.test(await page.locator('main').innerText()));
      }
    });
    // Model fit: the page only filters and sums the judged units of the demo snapshot.
    const fit = template.model_fit;
    const near = (actual, wanted, label) => assert(Math.abs(actual - wanted) < 1e-6, `${label}: ${actual} != ${wanted}`);
    const sum = (items, key) => items.reduce((total, item) => total + (item[key] || 0), 0);
    const fitWindow = async (page, pick = () => true) => {
      const from = await page.locator('#from').inputValue(), to = await page.locator('#to').inputValue();
      return fit.units.filter(u => u.date >= from && u.date <= to && pick(u));
    };
    async function fitTotals(page, units) {
      assert(units.length > 0, 'the scenario needs units');
      assert.equal(await page.locator('#fit-empty').isHidden(), true);
      const tile = Number(await page.locator('#fit-spend').getAttribute('data-value'));
      near(tile, sum(units, 'cost'), 'spend tile');
      const classes = await page.locator('#fit-classes .fit-track').evaluateAll(nodes => nodes.map(n => Number(n.dataset.cost)));
      near(classes.reduce((a, b) => a + b, 0), tile, 'classes add up to the tile');
      assert.equal(classes.length, new Set(units.map(u => u.class)).size);
      assert.equal(await page.locator('#fit-matrix tbody tr').count(), classes.length);
      assert.equal(await page.locator('#fit-matrix td.fit-rec').count(), classes.length);
      near(Number(await page.locator('#fit-over').getAttribute('data-value')), sum(units.filter(u => u.verdict === 'over'), 'cost'), 'over tile');
      near(Number(await page.locator('#fit-agents').getAttribute('data-value')), sum(units.filter(u => u.kind === 'agent'), 'cost'), 'subagent tile');
      near(Number(await page.locator('#fit-effort').getAttribute('data-value')), sum(units, 'save_effort'), 'effort tile');
    }
    const findings = page => page.locator('#fit-findings [data-finding]').evaluateAll(nodes => nodes.map(n => n.dataset.finding));
    const fitEmpty = async page => {
      assert.equal(await page.locator('#fit-empty').isVisible(), true);
      assert.equal(await page.locator('#fit-content').isHidden(), true);
      return page.locator('#fit-empty').innerText();
    };
    await check('model fit: tiles, charts, matrix, findings, sessions and readouts from the demo', template, async page => {
      assert.equal(fit.schema, 1);
      await page.click('#tab-fit');
      assert.equal(await page.locator('#tab-fit').getAttribute('aria-selected'), 'true');
      assert(await page.locator('#view-fit').isVisible());
      const units = await fitWindow(page);
      await fitTotals(page, units);
      assert.equal(await page.locator('#fit-cards .card').count(), 4);
      const tiers = ['fable', 'opus', 'sonnet', 'haiku', 'other'].filter(t => units.some(u => (u.tier || 'other') === t && u.cost > 0));
      assert.deepEqual(await page.locator('#fit-days-legend span').allTextContents(), tiers.map(t => t[0].toUpperCase() + t.slice(1)));
      assert(await page.locator('#fit-days svg path[data-tier]').count() >= new Set(units.filter(u => u.cost > 0).map(u => u.date)).size);
      assert.equal(await page.locator('#fit-days-table tbody tr').count(), new Set(units.filter(u => u.cost > 0).map(u => u.date)).size);
      assert.equal(await page.locator('#fit-classes-legend span').count(), 3);
      assert(await page.locator('#fit-efforts .fit-track').count() >= 2);
      const ids = await findings(page);
      for (const id of ['model-over', 'effort-over', 'agent-inherit', 'model-under', 'opus-xhigh', 'switches', 'cold-cache', 'big-context', 'haiku-long', 'effort-changes'])
        assert(ids.includes(id), id + ' finding');
      for (const id of ids) assert(await page.locator(`[data-finding="${id}"] tbody tr`).count() <= 8);
      const over = units.filter(u => u.verdict === 'over').sort((a, b) => b.save_model - a.save_model);
      assert.equal(await page.locator('[data-finding="model-over"] tbody tr').count(), Math.min(8, over.length));
      assert.match(await page.locator('[data-finding="model-over"] .fit-metric').textContent(), /Rough, upper bound/);
      const inherit = units.filter(u => u.kind === 'agent' && !u.explicit_model && u.verdict === 'over');
      assert.equal(await page.locator('[data-finding="agent-inherit"] tbody tr').count(), Math.min(8, inherit.length));
      assert.equal(await page.locator('#fit-sessions tbody tr').count(), Math.min(25, new Set(units.map(u => u.main_session)).size));
      assert.match(await page.locator('#fit-note').textContent(), /upper bounds/);
      // Hover and keyboard focus give the same readout.
      const track = page.locator('#fit-classes .fit-track').first();
      await track.hover();
      const hovered = await page.locator('#fit-tip').innerText();
      assert.match(hovered, /Spent/);
      await page.mouse.move(0, 0);
      assert.equal(await page.locator('#fit-tip').isHidden(), true);
      await track.focus();
      assert.equal(await page.locator('#fit-tip').innerText(), hovered);
      await page.locator('#fit-days .fit-hit').first().focus();
      assert.match(await page.locator('#fit-tip').innerText(), /Total/);
      // An example opens the existing session dialog.
      const example = page.locator('[data-finding="model-over"] [data-session]').first();
      const session = await example.getAttribute('data-session');
      assert.equal(session, over[0].session);
      await example.click();
      assert.equal(await page.locator('#session-dialog').evaluate(el => el.open), true);
      assert.equal(await page.locator('#session-title').textContent(), session);
      await page.keyboard.press('Escape');
    });
    await check('model fit follows the period, project, role, model and pool filters', template, async page => {
      await page.click('#tab-fit');
      await page.selectOption('#period', 'all');
      await fitTotals(page, await fitWindow(page));
      await page.selectOption('#period', '7');
      await page.click('#filter-toggle');
      await page.selectOption('#project', 'atlas-api');
      await fitTotals(page, await fitWindow(page, u => u.project === 'atlas-api'));
      assert(!(await page.locator('#fit-sessions tbody').innerText()).includes('design-system'));
      await page.selectOption('#project', '');
      await page.selectOption('#role', 'subagent');
      await fitTotals(page, await fitWindow(page, u => u.kind === 'agent'));
      assert.equal(await page.locator('#fit-agents .value').textContent(), '100%');
      for (const id of await findings(page)) assert(!['switches', 'cold-cache', 'big-context', 'effort-changes'].includes(id), id + ' is main-thread only');
      await page.selectOption('#role', 'main');
      await fitTotals(page, await fitWindow(page, u => u.kind === 'turn'));
      await page.selectOption('#role', 'review');
      assert.match(await fitEmpty(page), /auto-review/i);
      await page.selectOption('#role', '');
      await page.selectOption('#model', 'claude-opus-5');
      await fitTotals(page, await fitWindow(page, u => u.model === 'claude-opus-5'));
      assert.match(await page.locator('#fit-scope').textContent(), /Model filter/);
      assert.equal(await page.locator('[data-finding="big-context"], [data-finding="effort-changes"]').count(), 0);
      await page.selectOption('#model', 'gpt-6-astra');
      assert.match(await fitEmpty(page), /spent most of its cost on gpt-6-astra/);
      await page.selectOption('#model', '');
      await page.selectOption('#pool', 'interactive');
      await fitTotals(page, await fitWindow(page));
      assert.equal(await page.locator('[data-finding="big-context"]').count(), 0);
      await page.selectOption('#pool', 'managed');
      assert.match(await fitEmpty(page), /No Claude Code work matches these filters/);
      await page.click('#reset');
      await fitTotals(page, await fitWindow(page));
    });
    await check('model fit: a dated model ID from the model filter finds its units', template, async page => {
      const dated = 'claude-haiku-4-5-20251001';
      assert(template.rows.some(r => r.model === dated), 'the demo rows keep the dated ID');
      assert(fit.units.some(u => u.model === dated), 'units name the model as the rows do');
      await page.click('#tab-fit');
      await page.click('#filter-toggle');
      assert((await page.locator('#model option').allTextContents()).includes(dated));
      await page.selectOption('#model', dated);
      await fitTotals(page, await fitWindow(page, u => u.model === dated));
      assert.match(await page.locator('#fit-scope').textContent(), new RegExp('Model filter: .*' + dated));
      await page.selectOption('#period', 'all');
      await fitTotals(page, await fitWindow(page, u => u.model === dated));
    });
    await check('model fit: a provider without Claude and an invalid range show the empty state', template, async page => {
      await page.click('#tab-fit');
      await page.selectOption('#provider', 'Codex');
      assert.match(await fitEmpty(page), /Claude Code only/);
      await page.selectOption('#provider', 'Claude');
      await fitTotals(page, await fitWindow(page));
      await page.selectOption('#period', 'custom');
      await page.fill('#from', '2026-09-06'); await page.locator('#from').dispatchEvent('change');
      assert.match(await fitEmpty(page), /valid date range/);
      await page.fill('#from', '2026-01-01'); await page.locator('#from').dispatchEvent('change');
      await page.fill('#to', '2026-01-31'); await page.locator('#to').dispatchEvent('change');
      assert.match(await fitEmpty(page), /No Claude Code work/);
    });
    await check('model fit: a snapshot from an older collector shows the empty state', { ...template, model_fit: undefined }, async page => {
      assert.equal((await values(page)).length, 4);
      await page.click('#tab-fit');
      assert.match(await fitEmpty(page), /older collector/);
    });
    const hostile = '</script><img src=x onerror="window.__fitHacked=1">';
    const titled = structuredClone(fit);
    const largest = titled.units.filter(u => u.verdict === 'over' && u.date >= '2026-08-30').sort((a, b) => b.save_model - a.save_model)[0];
    largest.title = hostile + ' turn';
    await check('model fit: titles and session labels from the data render as text', { ...template, model_fit: titled,
      titles: { [titled.events.switches[0].session]: hostile + ' label' } }, async page => {
      await page.click('#tab-fit');
      const button = page.locator('[data-finding="model-over"] [data-session]').first();
      assert.equal(await button.textContent(), hostile + ' turn');
      assert.equal(await page.locator('[data-finding="switches"] [data-session]').first().textContent(), hostile + ' label');
      assert.equal(await page.locator('img').count(), 0);
      assert.equal(await page.evaluate(() => window.__fitHacked), undefined);
    });
    await check('model fit re-renders after a live update and empties without model_fit', template, async page => {
      await page.click('#tab-fit');
      const before = Number(await page.locator('#fit-spend').getAttribute('data-value'));
      const applied = await page.evaluate(() => {
        const next = structuredClone(D);
        next.sync_revision = '99999999999999999998';
        for (const u of next.model_fit.units) { u.cost *= 2; u.save_model *= 2; u.save_effort *= 2; }
        return applyLiveSnapshot(next);
      });
      assert.equal(applied, true);
      assert.equal(await page.locator('#tab-fit').getAttribute('aria-selected'), 'true');
      near(Number(await page.locator('#fit-spend').getAttribute('data-value')), 2 * before, 'live spend');
      assert.equal(await page.evaluate(() => { const next = structuredClone(D); delete next.model_fit;
        next.sync_revision = '99999999999999999999'; return applyLiveSnapshot(next); }), true);
      assert.match(await fitEmpty(page), /older collector/);
    });
    await check('model fit at phone width in the dark theme', template, async page => {
      await page.setViewportSize({ width: 375, height: 812 });
      await page.click('#theme');
      await page.click('#tab-fit');
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
      assert(!(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)), 'model fit overflows');
      assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--tier-fable').trim()), '#3987e5');
      assert.equal(await page.locator('#fit-days path[data-tier="fable"]').first().evaluate(n => getComputedStyle(n).fill), 'rgb(57, 135, 229)');
      const chart = await page.locator('#fit-days svg').evaluate(n => n.getBoundingClientRect().right <= n.parentElement.getBoundingClientRect().right + 1);
      assert(chart, 'the day chart fits its card');
      await page.click('#theme');
      assert.equal(await page.locator('#fit-days path[data-tier="fable"]').first().evaluate(n => getComputedStyle(n).fill), 'rgb(42, 120, 214)');
    });
    for (const [basis, label] of [['models_dev_rates', 'models.dev rates (2026-10-22) for all dates'],
                                  ['current_rates', 'Current rates (2026-10-22) for all dates'],
                                  ['custom_rates', 'Custom rates']]) {
      await check('visible snapshot time and price source: ' + basis,
        {price_basis: basis, price_as_of: '2026-10-22'}, async page => {
          assert.ok(await page.locator('header #subtitle').isVisible());
          assert.match(await page.locator('#subtitle').textContent(), /Snapshot 3\/10\/2026/);
          assert.ok((await page.locator('#money-note').textContent()).includes(label));
        });
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(network, []);
    console.log(`${passed} dashboard regression scenarios passed; no browser errors or network requests.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
