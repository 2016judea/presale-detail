"""Read today's by-owner car and boat listings off Craigslist.

curl-only, one request at a time per worker, cached by posting id.
Writes data/listings.json.
"""
import concurrent.futures as cf
import html
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
POSTS = ROOT / "data" / "cache" / "posts"
POSTS.mkdir(parents=True, exist_ok=True)
POST_TTL_HOURS = 20  # a renewal changes "updated"; re-read once a day

PHONE_RE = re.compile(r"(?<!\d)\(?([2-9]\d{2})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})(?!\d)")


def curl(url: str) -> str:
    for attempt in range(3):
        r = subprocess.run(["curl", "-sL", "--max-time", "30", "-A", UA, url],
                           capture_output=True, text=True)
        if r.returncode == 0 and len(r.stdout) > 2000:
            return r.stdout
        time.sleep(2 + attempt * 3)
    raise RuntimeError(f"fetch failed: {url}")


def search_url(cat: str) -> str:
    return (f"https://www.craigslist.org/search/area/{config.CITY}"
            f"?cat={cat}&purveyor=owner")


def search(kind: str, cat: str) -> list[dict]:
    h = curl(search_url(cat))
    rows = re.findall(
        r'<li class="cl-static-search-result" title="[^"]*">\s*<a href="([^"]+)">'
        r'.*?<div class="title">(.*?)</div>.*?<div class="price">([^<]*)</div>'
        r'.*?<div class="location">\s*(.*?)\s*</div>', h, re.S)
    out = []
    for url, title, price, loc in rows:
        out.append({"kind": kind, "url": url, "title": html.unescape(title).strip(),
                    "search_price": price.strip(), "location": html.unescape(loc).strip()})
    return out


def text_of(fragment: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", fragment)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(l.strip() for l in t.splitlines())).strip()


def parse_post(h: str, row: dict) -> dict | None:
    pid = re.search(r"post id: (\d+)", h)
    if not pid:
        return None
    times = re.findall(r'postinginfo reveal">(posted|updated): <time class="date timeago" datetime="([^"]+)"', h)
    tmap = {k: v for k, v in times}
    title = re.search(r'id="titletextonly"[^>]*>([^<]*)', h)
    price = re.search(r'<span class="price">([^<]*)</span>', h)
    body_m = re.search(r'<section id="postingbody">(.*?)</section>', h, re.S)
    body_html = body_m.group(1) if body_m else ""
    body_html = re.sub(r'<div class="print-information.*?</div>\s*</div>', "", body_html, flags=re.S)
    body = text_of(body_html)
    imgs = []
    for u in re.findall(r"https://images\.craigslist\.org/([A-Za-z0-9_]+?)_(?:\d+x\d+)\.jpg", h):
        if u not in imgs:
            imgs.append(u)
    attrs = {}
    for lab, val in re.findall(r'<span class="labl">([^<]*)</span>\s*<span class="valu">(.*?)</span>', h, re.S):
        attrs[lab.strip().rstrip(":")] = text_of(val)
    year = re.search(r'<span class="valu year">(\d{4})</span>', h)
    mm = re.search(r'<span class="valu makemodel">(.*?)</span>', h, re.S)
    lat = re.search(r'data-latitude="([^"]+)"', h)
    lon = re.search(r'data-longitude="([^"]+)"', h)
    notices = text_of("".join(re.findall(r'<ul class="notices">(.*?)</ul>', h, re.S)))
    phones = sorted({"(%s) %s-%s" % m for m in PHONE_RE.findall(body)})
    price_s = (price.group(1) if price else row.get("search_price", "")).replace("$", "").replace(",", "")
    try:
        price_n = int(float(price_s))
    except ValueError:
        price_n = None
    return {
        **row,
        "id": pid.group(1),
        "title": html.unescape(title.group(1)).strip() if title else row["title"],
        "price": price_n,
        "posted_at": tmap.get("posted"),
        "updated_at": tmap.get("updated") or tmap.get("posted"),
        "body": body[:4000],
        "photos": [f"https://images.craigslist.org/{u}_600x450.jpg" for u in imgs],
        "year": year.group(1) if year else attrs.get("year"),
        "make_model": text_of(mm.group(1)) if mm else None,
        "attrs": attrs,
        "lat": float(lat.group(1)) if lat else None,
        "lon": float(lon.group(1)) if lon else None,
        "phones": phones,
        "contact_in_post": 'class="show-contact"' in h,
        "no_solicitation": bool(re.search(r"unsolicited|no solicit", notices + body, re.I)),
        "notices": notices,
    }


def fetch_post(row: dict) -> dict | None:
    slug_id = row["url"].rstrip("/").rsplit("/", 1)[-1]
    p = POSTS / f"{slug_id}.html"
    fresh = p.exists() and (time.time() - p.stat().st_mtime) < POST_TTL_HOURS * 3600
    if not fresh:
        time.sleep(0.4)
        p.write_text(curl(row["url"]))
    return parse_post(p.read_text(), row)


FB = ROOT / "data" / "cache" / "fb"


def _js_str(raw: str) -> str:
    return json.loads('"' + raw + '"')


def _nearest(h: str, pat: str, at: int):
    best = None
    for m in re.finditer(pat, h):
        if best is None or abs(m.start() - at) < abs(best.start() - at):
            best = m
    return best


def parse_fb(item_id: str, kind: str) -> dict | None:
    """One Marketplace item page (saved by scripts/fetch_fb.js) -> a listing row."""
    p = FB / f"{item_id}.html"
    if not p.exists():
        return None
    h = p.read_text()
    # The page also carries ~20 "related" listings; the item's own block is the
    # title match with the item id beside it. Its other fields sit within ~30k chars.
    t = next((m for m in re.finditer(r'"marketplace_listing_title":"((?:[^"\\]|\\.)*)"', h)
              if f'"id":"{item_id}"' in h[max(0, m.start() - 4000): m.start() + 4000]), None)
    if not t:
        return None
    at = t.start()
    win = h[max(0, at - 30000): at + 30000]
    mid = at - max(0, at - 30000)
    if (m := _nearest(win, r'"is_sold":(true|false)', mid)) and m.group(1) == "true":
        return None
    if (m := _nearest(win, r'"is_pending":(true|false)', mid)) and m.group(1) == "true":
        return None
    price = _nearest(win, r'"listing_price":\{"amount_with_offset":"\d+","currency":"USD","amount":"([\d.]+)"', mid)
    created = _nearest(win, r'"creation_time":(\d+)', mid)
    loc = _nearest(win, r'"location_text":\{"text":"((?:[^"\\]|\\.)*)"', mid)
    desc = re.search(r'"redacted_description":\{"text":"((?:[^"\\]|\\.)*)"', h)
    photos = []
    i = h.find('"listing_photos":[')
    if i >= 0:
        block = h[i:i + 40000]
        block = block[: block.find("]}") + 1] if "]}" in block else block
        for u in re.findall(r'"image":\{"height":\d+,"width":\d+,"uri":"([^"]+)"', block):
            u = _js_str(u)
            if u not in photos:
                photos.append(u)
    seller = re.search(r'"vehicle_seller_type":"([A-Z_]+)"', h)
    make = re.search(r'"vehicle_make_display_name":"((?:[^"\\]|\\.)*)"', h)
    model = re.search(r'"vehicle_model_display_name":"((?:[^"\\]|\\.)*)"', h)
    ts = (datetime.fromtimestamp(int(created.group(1)), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
          if created else None)
    body = _js_str(desc.group(1)) if desc else ""
    title = _js_str(t.group(1))
    return {
        "source": "facebook", "kind": kind, "id": f"fb{item_id}",
        "url": f"https://www.facebook.com/marketplace/item/{item_id}/",
        "title": title, "price": int(float(price.group(1))) if price else None,
        "location": _js_str(loc.group(1)) if loc else "",
        "posted_at": ts, "updated_at": ts, "body": body[:4000], "photos": photos,
        "year": (re.match(r"(19|20)\d\d", title) or [None])[0],
        "make_model": " ".join(x for x in [_js_str(make.group(1)) if make else "",
                                           _js_str(model.group(1)) if model else ""] if x) or None,
        "attrs": {"seller type": seller.group(1)} if seller else {},
        "lat": None, "lon": None, "phones": [], "contact_in_post": True,
        "no_solicitation": False, "notices": "",
    }


def _norm_title(t: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) > 1}


def same_vehicle(a: dict, b: dict) -> bool:
    """The same vehicle cross-posted: same asking price and mostly the same title words."""
    if not a["price"] or a["price"] != b["price"]:
        return False
    x, y = _norm_title(a["title"]), _norm_title(b["title"])
    return bool(x and y) and len(x & y) / min(len(x), len(y)) >= 0.6


def main():
    rows = []
    for kind, cat in config.SECTIONS.items():
        got = search(kind, cat)
        print(f"{kind}: {len(got)} rows on the search page", flush=True)
        rows += got[: config.MAX_PER_SECTION]
    out, failed = [], 0
    with cf.ThreadPoolExecutor(3) as ex:
        for r in ex.map(lambda r: _safe(fetch_post, r), rows):
            if r:
                out.append(r)
            else:
                failed += 1
    for r in out:
        r["source"] = "craigslist"
    idx = FB / "index.json"
    fb = []
    if idx.exists():
        for item_id, kind in json.loads(idx.read_text()).items():
            if r := parse_fb(item_id, kind):
                fb.append(r)
    dupes = 0
    for f in fb:
        twin = next((c for c in out if c["source"] == "craigslist" and same_vehicle(c, f)), None)
        if twin:
            twin["also"] = {"source": "facebook", "url": f["url"]}
            dupes += 1
        else:
            out.append(f)
    print(f"facebook: {len(fb)} live listings parsed, {dupes} already on Craigslist", flush=True)
    seen, uniq = set(), []
    for r in out:
        if r["id"] not in seen:
            seen.add(r["id"])
            uniq.append(r)
    doc = {"city": config.CITY, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "listings": uniq}
    (ROOT / "data" / "listings.json").write_text(json.dumps(doc, indent=1))
    print(f"parsed {len(uniq)} listings, {failed} failed", flush=True)


def _safe(fn, r):
    try:
        return fn(r)
    except Exception as e:  # one bad page never stops the run
        print("  skip", r["url"], e, file=sys.stderr)
        return None


if __name__ == "__main__":
    main()
