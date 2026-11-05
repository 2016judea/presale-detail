// Facebook Marketplace search for local detailing-service listings, logged out,
// headless. Saves item pages to data/cache/services/fb/<id>.html + index.json
// (id -> the query that found it). scripts/price_table.py parses them.
const fs = require("fs"), path = require("path"), os = require("os");
const { chromium } = require(process.env.PLAYWRIGHT_PATH ||
  path.join(os.homedir(), "Desktop/workspace/pricing-vintage-baseball-cards/node_modules/playwright"));
const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "data/cache/services/fb");
fs.mkdirSync(OUT, { recursive: true });
const CITY = fs.readFileSync(path.join(ROOT, "config.py"), "utf8").match(/^CITY = "([^"]+)"/m)[1];
const QUERIES = ["car detailing", "auto detailing", "mobile detailing", "boat detailing",
  "paint correction", "buffing", "oxidation removal", "headlight restoration", "interior detailing", "gelcoat"];
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 }, userAgent: UA })).newPage();
    const index = {};
    for (const q of QUERIES) {
      await page.goto(`https://www.facebook.com/marketplace/${CITY}/search?query=${encodeURIComponent(q)}`, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(4000);
      const close = await page.$('div[aria-label="Close"]'); if (close) await close.click().catch(() => {});
      for (let i = 0; i < 4; i++) { await page.mouse.wheel(0, 4000); await page.waitForTimeout(1200); }
      const ids = await page.evaluate(() => [...new Set([...document.querySelectorAll('a[href*="/marketplace/item/"]')]
        .map(a => (a.href.match(/item\/(\d+)/) || [])[1]).filter(Boolean))]);
      console.log(`${q}: ${ids.length}`);
      for (const id of ids) index[id] = index[id] || q;
    }
    let n = 0;
    for (const id of Object.keys(index)) {
      const f = path.join(OUT, `${id}.html`);
      if (fs.existsSync(f)) continue;
      try {
        const r = await page.goto(`https://www.facebook.com/marketplace/item/${id}/`, { waitUntil: "domcontentloaded" });
        fs.writeFileSync(f, await r.text()); n++;
      } catch (e) { console.error("skip", id, e.message); }
      await page.waitForTimeout(1000);
    }
    fs.writeFileSync(path.join(OUT, "index.json"), JSON.stringify(index, null, 1));
    console.log(`${Object.keys(index).length} items, ${n} fetched`);
  } finally { await browser.close(); }
})();
