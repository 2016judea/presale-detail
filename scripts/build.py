"""Rank today's listings and write site/index.html (data embedded, no fetch)."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

A = ROOT / "data" / "assessments"


def parse_t(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z") if s else None


def real_price(n):
    """Placeholder prices ($1, $123,456,789, $12345) are not prices."""
    if not n or n < 300 or n > 400_000:
        return None
    if str(n) in "1234567890" or len(set(str(n))) == 1:
        return None
    return n


def score(l, a, now, fallback):
    """detail-need x listing price x freshness. Boats win ties (sort key)."""
    need = (a["need_score"] / 10) ** 2  # squared: the visible gap is the pitch, so it leads
    price = min(max(real_price(l["price"]) or fallback, 1000), 60000)
    price_w = (price / 60000) ** (1 / 3)  # more money riding, but need leads: a $60k boat is ~4x a $1k beater, not 60x
    last = parse_t(l["updated_at"]) or now
    days = max((now - last).total_seconds() / 86400, 0)
    fresh = 1 / (1 + days / 4)
    return need * price_w * fresh


def main():
    doc = json.loads((ROOT / "data" / "listings.json").read_text())
    now = datetime.now(timezone.utc)
    prices = sorted(p for l in doc["listings"] if (p := real_price(l["price"])))
    fallback = prices[len(prices) // 2] if prices else 5000  # unknown price ranks at the median
    cards = []
    for l in doc["listings"]:
        p = A / f"{l['id']}.json"
        if not p.exists():
            continue
        a = json.loads(p.read_text())
        if not a.get("fit") or not a.get("message") or a["need_score"] < 4:
            continue
        cards.append({
            "id": l["id"], "kind": l["kind"], "title": l["title"], "price": real_price(l["price"]),
            "location": l["location"], "url": l["url"],
            "photo": l["photos"][0] if l["photos"] else None,
            "posted_at": l["posted_at"], "updated_at": l["updated_at"],
            "need": a["need_score"], "findings": a["findings"], "services": a["services"],
            "message": a["message"], "contact_in_post": l["contact_in_post"],
            "phones": l["phones"], "source": l.get("source", "craigslist"), "also": l.get("also"),
            "score": round(score(l, a, now, fallback), 3),
        })
    cards.sort(key=lambda c: (-round(c["score"], 2), c["kind"] != "boat", -c["need"]))
    meta = {"city": doc["city"], "fetched_at": doc["fetched_at"],
            "read": len(doc["listings"]), "shown": len(cards)}
    tpl = (ROOT / "scripts" / "page.html").read_text()
    page = (tpl.replace("/*DATA*/null", json.dumps({"meta": meta, "cards": cards}))
               .replace("{{CITY}}", doc["city"].title()))
    (ROOT / "site" / "index.html").write_text(page)
    print(f"read {meta['read']}, shown {meta['shown']}")
    for c in cards[:3]:
        print(f"  {c['score']:.3f} need {c['need']} {'$%s' % format(c['price'], ',') if c['price'] else 'no price'} {c['kind']}: {c['title']}")


if __name__ == "__main__":
    main()
