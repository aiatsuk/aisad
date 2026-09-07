// Synthetic end-to-end provenance, navigation and offline behavior checks.
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const { chromium } = require('playwright');

const fixture = spawnSync(process.env.PYTHON || 'python3', ['-c', `
import agent_usage as app
from test_evidence import EvidenceTests
t=EvidenceTests();t.setUp()
try:
    t.write('.codex/sessions/root.jsonl',t.trace())
    t.write('.codex/sessions/child.jsonl',t.trace('child','root'))
    t.write('.claude/projects/p/only-events.jsonl',[dict(type='user',uuid='solo',timestamp='2026-01-01T12:00:00Z',message={'content':'PRIVATE_PROMPT'})])
    snap=app.make_snapshot(t.args(),dashboard=True,include_requests=True)
    snap.pop('sources',None)
    for key in ['requests','events','source_files','tool_calls','turns']:snap.pop(key,None)
    snap.update(as_of_date='2026-09-07',demo=True,titles={'Codex:root':'Readable title'})
    print(app.render_html(snap))
finally:t.doCleanups()
`], { cwd: path.resolve(__dirname, '..'), encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 });
assert.equal(fixture.status, 0, fixture.stderr);
assert(!fixture.stdout.includes('PRIVATE_PROMPT'));

(async () => {
  const browser = await chromium.launch({ headless: true });
  const errors = [], network = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.on('pageerror', e => errors.push(String(e)));
    page.on('request', r => network.push(r.url()));
    await page.clock.install();
    await page.setContent(fixture.stdout);
    await page.waitForSelector('#interactive-dashboard', { state: 'visible' });
    await page.locator('#daily [data-day]').first().focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#tab-sessions').getAttribute('aria-selected'), 'true');
    assert.equal(await page.locator('#from').inputValue(), '2026-09-07');
    await page.locator('[data-session="Codex:root"]').first().click();
    assert.equal(await page.locator('#session-title').textContent(), 'Readable title');
    assert.match(await page.locator('#session-lifecycle').textContent(), /Active time is unavailable/);
    assert.match(await page.locator('#session-lifecycle').textContent(), /turn_completed/);
    assert.match(await page.locator('#session-lifecycle').textContent(), /No fresh input observation/);
    assert.equal(await page.locator('#events-table tbody tr').count(), 10);
    assert.match(await page.locator('#events-table').textContent(), /error recorded/);
    await page.locator('#session-timeline [data-observation]').first().focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#observation-detail').isVisible(), true);
    assert.match(await page.locator('#observation-detail').textContent(), /line 6 · byte/);
    assert.match(await page.locator('#observation-detail').textContent(), /Measured input: 1,000/);
    await page.locator('#session-lifecycle [data-session="Codex:child"]').click();
    assert.equal(await page.locator('#session-title').textContent(), 'Codex:child');
    await page.click('#close-session');
    await page.click('#reset');
    await page.click('#tab-context');
    await page.locator('#context-chart [data-value="Codex:root"]').click();
    assert.equal(await page.locator('#session-title').textContent(), 'Readable title');
    await page.click('#close-session');
    await page.selectOption('#period', 'all');
    assert.equal(await page.locator('#from').inputValue(), '2026-01-01');
    await page.click('#tab-sessions');
    await page.locator('[data-session="Claude:only-events"]').click();
    assert.match(await page.locator('#session-timeline').textContent(), /No usage observations/);
    assert.equal(await page.locator('#events-table tbody tr').count(), 1);
    await page.click('#close-session');
    await page.selectOption('#provider', 'Codex');
    assert.equal(await page.locator('#sessions-table tbody tr').count(), 2);
    await page.clock.fastForward(120000);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('[data-session="Codex:root"]').first().click();
    assert(!(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)));
    assert.deepEqual(errors, []);
    assert.deepEqual(network, []);
    console.log('Session evidence, source drill-down, event-only history, keyboard navigation and offline behavior passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
