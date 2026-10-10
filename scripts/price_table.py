"""Build data/price_table.json: what Twin Cities detailers charge, read off their own ads.

Sources: Craigslist services searches (data/cache/services/posts, s_*.html) and
Facebook Marketplace service listings (data/cache/services/fb, scripts/fetch_fb_services.js).

A model reads each ad and lists the prices it states, each with the exact words it
came from. Code keeps a price only if those words are in the ad and contain the number,
so every figure in the table is a competitor's own, never a model's. One seller who
posts the same ad several times counts once per (tier, size).
"""
import hashlib
import html
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import config  # noqa: E402
from assess import client  # noqa: E402  (same key lookup)

SVC = ROOT / "data" / "cache" / "services"
EXTRACT = ROOT / "data" / "price_extractions"
EXTRACT.mkdir(parents=True, exist_ok=True)

TIERS = {
    "car_interior": "flat", "car_wash_wax": "flat", "car_full": "flat",
    "paint_correction": "flat", "headlight": "flat", "touch_up": "flat",
    "boat_wash_wax": "per_foot", "boat_oxidation": "per_foot",
}
LABEL = {
    "car_interior": "Car interior detail", "car_wash_wax": "Car exterior wash + wax",
    "car_full": "Full detail (inside + out)", "paint_correction": "Paint correction / buff",
    "headlight": "Headlight restoration (pair)", "touch_up": "Touch-up (per area)",
    "boat_wash_wax": "Boat wash + wax (per ft)", "boat_oxidation": "Boat oxidation removal / compound (per ft)",
}
RELEVANT = re.compile(r"detail|headlight|buff|oxid|gelcoat|polish|ceramic|wax|paint correction|interior clean", re.I)

SYSTEM = """You read one ad for a local car/boat detailing service and list every price it \
states for a detailing service, plus any stated job duration. Do not infer or estimate; \
only report what the ad literally says.

For each price:
- tier: car_interior (interior only), car_wash_wax (exterior wash/wax only), car_full \
(interior + exterior package), paint_correction (buff, polish, swirl/scratch removal, \
paint correction; NOT ceramic coating alone), headlight (headlight restoration), touch_up \
(paint chip / scratch touch-up per spot or panel), boat_wash_wax, boat_oxidation (boat \
compound / oxidation removal / gelcoat restoration), or other (ceramic coating, tint, \
mechanical, anything else).
- size: small, mid, large, any (when one price covers all), or boat.
- unit: flat or per_foot.
- price: the number as written.
- starting_at: true when the ad says "starting at", "from", "as low as" or similar.
- quote: the exact words from the ad containing that price, copied character for \
character (a short span, under 120 characters).

For each duration, the tier, the hours stated, and the exact words."""

SCHEMA = {
    "type": "object",
    "properties": {
        "prices": {"type": "array", "items": {"type": "object", "properties": {
            "tier": {"type": "string", "enum": list(TIERS) + ["other"]},
            "size": {"type": "string", "enum": ["small", "mid", "large", "any", "boat"]},
            "unit": {"type": "string", "enum": ["flat", "per_foot"]},
            "price": {"type": "number"},
            "starting_at": {"type": "boolean"},
            "quote": {"type": "string"}},
            "required": ["tier", "size", "unit", "price", "starting_at", "quote"],
            "additionalProperties": False}},
        "durations": {"type": "array", "items": {"type": "object", "properties": {
            "tier": {"type": "string", "enum": list(TIERS) + ["other"]},
            "hours": {"type": "number"},
            "quote": {"type": "string"}},
            "required": ["tier", "hours", "quote"], "additionalProperties": False}},
    },
    "required": ["prices", "durations"],
    "additionalProperties": False,
}


def js(raw):
    return json.loads('"' + raw + '"')


def cl_ads():
    rows = {}
    for f in SVC.glob("s_*.html"):
        h = f.read_text()
        for t, u in re.findall(r'<li class="cl-static-search-result" title="([^"]*)">\s*<a href="([^"]+)"', h):
            rows[u] = html.unescape(t)
    for u, title in rows.items():
        p = SVC / "posts" / (u.rstrip("/").rsplit("/", 1)[-1] + ".html")
        if not p.exists():
            continue
        h = p.read_text()
        m = re.search(r'<section id="postingbody">(.*?)</section>', h, re.S)
        b = re.sub(r'<div class="print-information.*?</div>\s*</div>', "", m.group(1) if m else "", flags=re.S)
        b = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", b))).strip()
        phone = re.search(r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}", b)
        # Same seller, several posts: key on the phone, else on the title minus its numbers.
        seller = (re.sub(r"\D", "", phone.group(0)) if phone
                  else re.sub(r"[\d$.,\s]+", " ", title.lower()).strip())
        yield {"source": "craigslist", "url": u, "title": title, "text": b, "seller": "cl:" + seller,
               "location": "Twin Cities (Craigslist Minneapolis)"}


def fb_ads():
    idx = SVC / "fb" / "index.json"
    if not idx.exists():
        return
    for iid in json.loads(idx.read_text()):
        p = SVC / "fb" / f"{iid}.html"
        if not p.exists():
            continue
        h = p.read_text()
        t = next((m for m in re.finditer(r'"marketplace_listing_title":"((?:[^"\\]|\\.)*)"', h)
                  if f'"id":"{iid}"' in h[max(0, m.start() - 4000): m.start() + 4000]), None)
        if not t:
            continue
        win = h[max(0, t.start() - 30000): t.start() + 30000]
        d = re.search(r'"redacted_description":\{"text":"((?:[^"\\]|\\.)*)"', h)
        loc = re.search(r'"location_text":\{"text":"((?:[^"\\]|\\.)*)"', win)
        seller = re.search(r'"marketplace_listing_seller":\{"__typename":"User","name":"(?:[^"\\]|\\.)*","id":"([^"]+)"', h)
        price = re.search(r'"formatted_price":\{"text":"([^"]*)"', win)
        title = js(t.group(1))
        text = js(d.group(1)) if d else ""
        if price and "$" in price.group(1):
            text = f"Listed price: {js(price.group(1))}\n{text}"
        yield {"source": "facebook", "url": f"https://www.facebook.com/marketplace/item/{iid}/",
               "title": title, "text": text, "seller": "fb:" + (seller.group(1) if seller else iid),
               "location": js(loc.group(1)) if loc else ""}


def norm(s):
    return re.sub(r"\s+", " ", s).strip().lower()


def extract(ad):
    key = hashlib.md5(ad["url"].encode()).hexdigest()
    p = EXTRACT / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text())
    r = client.messages.create(
        model=config.MODEL, max_tokens=4000, system=SYSTEM,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": f"Title: {ad['title']}\n\n{ad['text'][:5000]}"}])
    out = json.loads(next(b.text for b in r.content if b.type == "text"))
    out["url"] = ad["url"]
    p.write_text(json.dumps(out, indent=1))
    return out


def verified(item, ad):
    """The quoted words must be in the ad, and the number must be in the quoted words."""
    q = norm(item["quote"])
    if not q or q not in norm(ad["title"] + "\n" + ad["text"]):
        return False
    n = item.get("price", item.get("hours"))
    forms = {f"{n:g}", f"{n:,.0f}", f"{n:.2f}"}
    return any(f in item["quote"] for f in forms)


def main():
    ads = [a for a in list(cl_ads()) + list(fb_ads())
           if RELEVANT.search(a["title"] + " " + a["text"])
           and re.search(r"\d", a["text"] + a["title"])]
    # Local only: Facebook search leaks other states; keep Minnesota.
    ads = [a for a in ads if a["source"] == "craigslist" or a["location"].endswith(", MN")]
    with_price = [a for a in ads if re.search(r"\$\s?\d|\b\d{2,4}\s?(?:\$|dollars)|\(\D{0,20}\d{2,4}\)", a["title"] + " " + a["text"])]
    print(f"{len(ads)} local detailing ads, {len(with_price)} state a price-like number")
    seen, prices, hours, rejected = set(), {t: [] for t in TIERS}, {t: [] for t in TIERS}, 0
    for ad in with_price:
        ex = extract(ad)
        for it in ex["prices"]:
            if it["tier"] not in TIERS or it["unit"] != TIERS[it["tier"]]:
                continue
            if not verified(it, ad):
                rejected += 1
                continue
            if re.search(r"\badd\b|add-on|addon|additional", it["quote"], re.I):
                continue  # an add-on to a package is not a price for the service
            price = it["price"]
            if it["tier"] == "headlight" and re.search(r"per (side|light|lens|headlight)|each", it["quote"], re.I):
                price = price * 2  # the table is per pair
            it = {**it, "price": price}
            k = (ad["seller"], it["tier"], it["size"], it["price"])
            if k in seen:
                continue
            seen.add(k)
            prices[it["tier"]].append({"price": it["price"], "size": it["size"],
                                       "starting_at": it["starting_at"], "quote": it["quote"],
                                       "url": ad["url"], "source": ad["source"], "seller": ad["seller"]})
        for it in ex["durations"]:
            if it["tier"] in TIERS and verified(it, ad):
                hours[it["tier"]].append({"hours": it["hours"], "quote": it["quote"], "url": ad["url"]})
    table = {}
    for t, rows in prices.items():
        # One price per seller, so a seller listing six package sizes counts once:
        # their mid-size (or one-size) price, else the median of what they list.
        per_seller = {}
        for sel in {r["seller"] for r in rows}:
            mine = [r for r in rows if r["seller"] == sel]
            pick = ([r["price"] for r in mine if r["size"] == "mid"]
                    or [r["price"] for r in mine if r["size"] in ("any", "boat")]
                    or [r["price"] for r in mine])
            per_seller[sel] = statistics.median(pick)
        vals = sorted(per_seller.values())
        med = statistics.median(vals) if vals else None
        table[t] = {
            "label": LABEL[t], "unit": TIERS[t], "n": len(vals), "prices_stated": len(rows),
            "median": med, "thin": len(vals) < 3, "per_seller": vals,
            "sources": sorted({r["url"] for r in rows}), "prices": rows,
            "stated_hours": hours[t],
        }
    doc = {"built_from": {"ads_read": len(ads), "ads_with_prices": len(with_price),
                          "quotes_rejected_unverified": rejected},
           "tiers": table}
    (ROOT / "data" / "price_table.json").write_text(json.dumps(doc, indent=1))
    for t, r in table.items():
        print(f"  {t:17} n={r['n']} sellers ({r['prices_stated']} prices) median={r['median']} {'THIN' if r['thin'] else ''}")
    print(f"  rejected {rejected} prices whose quote didn't verify")


if __name__ == "__main__":
    main()
