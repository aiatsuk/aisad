// Development only. Requires Playwright and its Chromium browser.
// Run `python3 scripts/make_demo.py` first, then `node scripts/capture_demo.cjs`.
const assert = require('node:assert/strict');
const { mkdir } = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1200 },
      locale: 'en-US', timezoneId: 'UTC', colorScheme: 'light', deviceScaleFactor: 1 });
    const errors = [], requests = [];
    page.on('pageerror', error => errors.push(String(error)));
    page.on('request', request => { if (!request.url().startsWith('file:')) requests.push(request.url()); });
    await page.goto(pathToFileURL(path.join(root, 'output/demo/dashboard.html')).href);
    await page.waitForSelector('#cards .value');
    assert.equal(await page.locator('html').getAttribute('lang'), 'en');
    assert.equal(await page.locator('.badge').textContent(), 'Synthetic demo');
    assert(!/[\u0400-\u04ff]/.test(await page.locator('body').textContent()));
    const base = await page.locator('#cards .value').allTextContents();
    assert.equal(base.length, 6);
    assert(await page.locator('svg rect').count() > 0);
    await page.selectOption('#provider', 'Claude');
    assert.notEqual((await page.locator('#cards .value').allTextContents())[2], base[2]);
    await page.selectOption('#model', 'claude-opus-5');
    const models = await page.locator('#models-table tbody td:first-child').allTextContents();
    assert.deepEqual(models, ['claude-opus-5']);
    await page.click('#reset');
    await page.fill('#search', 'no-matching-session');
    assert.equal(await page.locator('#sessions-table tbody tr').count(), 0);
    assert.deepEqual(await page.locator('#cards .value').allTextContents(), base);
    await page.click('#reset');
    await page.selectOption('#chartmetric', 'requests');
    assert.equal(await page.locator('#daily svg').getAttribute('aria-label'), 'Requests by day');
    await page.selectOption('#chartmetric', 'cost');
    await page.locator('#chartmetric').blur();
    const height = await page.locator('.grid.equal').evaluate(element => Math.ceil(element.getBoundingClientRect().bottom + 12));
    await page.setViewportSize({ width: 1440, height });
    await mkdir(path.join(root, 'docs'), { recursive: true });
    await page.screenshot({ path: path.join(root, 'docs/dashboard.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('summary').click();
    assert(!(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)));
    assert.deepEqual(errors, []);
    assert.deepEqual(requests, []);
    console.log('English UI, filters, charts, mobile layout and offline rendering passed. Saved docs/dashboard.png.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
