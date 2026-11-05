// Read Facebook Marketplace vehicle + boat listings for config CITY, logged out,
// in headless Chromium. Saves each item page's HTML to data/cache/fb/<id>.html
// and the id -> kind map to data/cache/fb/index.json. scripts/fetch.py parses them.
//
// Logged out is enough: category pages render ~50 items each, and item pages carry
// the listing JSON (title, price, photos, description, creation time). No account,
// no cookies, no visible window; the browser is closed at the end.
//
// Playwright: set PLAYWRIGHT_PATH, else the copy at ~/Desktop/pricing-vintage-baseball-cards.
const fs = require("fs");
const path = require("path");
const os = require("os");
const pw = process.env.PLAYWRIGHT_PATH ||
  path.join(os.homedir(), "Desktop/workspace/pricing-vintage-baseball-cards/node_modules/playwright");
const { chromium } = require(pw);

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "data/cache/fb");
fs.mkdirSync(OUT, { recursive: true });
const CITY = fs.readFileSync(path.join(ROOT, "config.py"), "utf8").match(/^CITY = "([^"]+)"/m)[1];
const FB_CITY = process.env.FB_CITY || CITY;  // FB's slug; same as Craigslist's for minneapolis
const CATS = { boats: "boat", cars: "car", trucks: "car" };
const MAX = Number(process.env.FB_MAX || 150);
const TTL_MS = 20 * 3600 * 1000;
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, userAgent: UA });
    const page = await ctx.newPage();
    const index = {};
    for (const [cat, kind] of Object.entries(CATS)) {
      const url = `https://www.facebook.com/marketplace/${FB_CITY}/${cat}?sortBy=creation_time_descend`;
      const r = await page.goto(url, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(4000);
      // the logged-out "See more on Facebook" modal stops the feed loading more; dismiss it
      const close = await page.$('div[aria-label="Close"]');
      if (close) await close.click().catch(() => {});
      for (let i = 0; i < 8; i++) { await page.mouse.wheel(0, 4000); await page.waitForTimeout(1500); }
      const ids = await page.evaluate(() => [...new Set([...document.querySelectorAll('a[href*="/marketplace/item/"]')]
        .map(a => (a.href.match(/item\/(\d+)/) || [])[1]).filter(Boolean))]);
      console.log(`${cat}: HTTP ${r.status()}, ${ids.length} items`);
      for (const id of ids) if (!index[id]) index[id] = kind;
    }
    const ids = Object.keys(index).slice(0, MAX);
    let fetched = 0, cached = 0, failed = 0;
    for (const id of ids) {
      const f = path.join(OUT, `${id}.html`);
      if (fs.existsSync(f) && Date.now() - fs.statSync(f).mtimeMs < TTL_MS) { cached++; continue; }
      try {
        const r = await page.goto(`https://www.facebook.com/marketplace/item/${id}/`, { waitUntil: "domcontentloaded" });
        const html = await r.text();
        if (!html.includes("marketplace_listing_title")) throw new Error(`no listing JSON (HTTP ${r.status()})`);
        fs.writeFileSync(f, html);
        fetched++;
      } catch (e) {
        failed++;
        console.error("  skip", id, e.message);
      }
      await page.waitForTimeout(1200);
    }
    fs.writeFileSync(path.join(OUT, "index.json"), JSON.stringify(Object.fromEntries(ids.map(i => [i, index[i]])), null, 1));
    console.log(`facebook: ${ids.length} items, ${fetched} fetched, ${cached} cached, ${failed} failed`);
  } finally {
    await browser.close();
  }
})();
