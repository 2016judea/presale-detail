"""Quote, rank and write site/index.html (data embedded, no fetch).

Rank = quote $ / estimated hours (highest return on their time first), ties broken by
need score, then freshness. Cards with no computable quote go after the quoted ones.
Every count and dollar figure on the page is computed here from the cards."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import config  # noqa: E402
import quote as Q  # noqa: E402

A = ROOT / "data" / "assessments"
O = ROOT / "data" / "openers"
UPSIDE = "A clean detail gives you room to ask more, or a better chance of selling at your price."


def parse_t(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z") if s else None


def real_price(n):
    """Placeholder prices ($1, $123,456,789, $12345) are not prices."""
    if not n or n < 300 or n > 400_000:
        return None
    if str(n) in "1234567890" or len(set(str(n))) == 1:
        return None
    return n


def join_and(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def message(opener, q, kind):
    priced = [x for x in q["lines"] if x["amount"]]
    parts = [opener, UPSIDE]
    if q["total"]:
        size = ""
        if kind == "boat" and q["boat_length_src"] == "default":
            size = f" for a boat up to {config.BOAT_LENGTH_DEFAULT_FT:g} ft"
        parts.append(f"We can do it for ${q['total']}{size}, which includes {join_and([x['name'] for x in priced])}, and we come to you.")
        extra = [x["name"] for x in q["lines"] if not x["amount"]]
        if extra:
            parts.append(f"If you'd like {join_and(extra)} too, we can price that when we see it.")
        parts.append("Want to pick a time this week?")
    else:
        parts.append("We come to you. Want me to send a price?")
    return " ".join(parts)


def main():
    doc = json.loads((ROOT / "data" / "listings.json").read_text())
    now = datetime.now(timezone.utc)
    cards = []
    for l in doc["listings"]:
        p = A / f"{l['id']}.json"
        if not p.exists():
            continue
        a = json.loads(p.read_text())
        if not a.get("fit") or a["need_score"] < 4:
            continue
        op = O / f"{l['id']}.json"
        opener = json.loads(op.read_text())["text"] if op.exists() else ""
        if not opener:
            continue
        q = Q.quote(l, a)
        last = parse_t(l["updated_at"]) or now
        posted = parse_t(l["posted_at"]) or last
        cards.append({
            "id": l["id"], "kind": l["kind"], "title": l["title"], "price": real_price(l["price"]),
            "location": l["location"], "url": l["url"],
            "photo": l["photos"][0] if l["photos"] else None,
            "posted_at": l["posted_at"], "updated_at": l["updated_at"],
            "new24": (now - posted).total_seconds() < 86400,
            "need": a["need_score"], "findings": a["findings"],
            "message": message(opener, q, l["kind"]),
            "contact_in_post": l["contact_in_post"], "phones": l["phones"],
            "source": l.get("source", "craigslist"), "also": l.get("also"),
            "quote": q, "days_idle": round((now - last).total_seconds() / 86400, 2),
        })
    cards.sort(key=lambda c: (c["quote"]["per_hour"] is None, -(c["quote"]["per_hour"] or 0),
                              -c["need"], c["days_idle"]))

    # Counts for every filter combination, so the tabs and the header line follow the
    # active filters without the page doing any arithmetic of its own.
    counts = {}
    for kind in ("all", "car", "boat"):
        for src in ("all", "craigslist", "facebook"):
            ok = lambda x: (kind == "all" or x["kind"] == kind) and (src == "all" or x.get("source", "craigslist") == src)
            cs = [c for c in cards if ok(c)]
            counts[f"{kind}|{src}"] = {
                "read": sum(1 for l in doc["listings"] if ok(l)),
                "shown": len(cs),
                "quotes": sum(c["quote"]["total"] or 0 for c in cs),
                "unquoted": sum(1 for c in cs if not c["quote"]["total"]),
                "new24": sum(1 for c in cs if c["new24"]),
            }
    prices = [{"tier": t, "quote": Q.unit_price(t)[0], "hours": Q.tier_hours(t)} for t in Q.AI]
    meta = {"city": doc["city"], "fetched_at": doc["fetched_at"], "counts": counts, "prices": prices}
    tpl = (ROOT / "scripts" / "page.html").read_text()
    page = (tpl.replace("/*DATA*/null", json.dumps({"meta": meta, "cards": cards}))
               .replace("/*READER_EVENTS*/", (ROOT / "scripts" / "reader_events.js").read_text())
               .replace("{{CITY}}", doc["city"].title()))
    (ROOT / "site" / "index.html").write_text(page)
    c = counts["all|all"]
    print(f"read {c['read']}, shown {c['shown']}, ${c['quotes']:,} in quotes, {c['unquoted']} unquoted, {c['new24']} new in 24h")
    for x in cards[:3]:
        q = x["quote"]
        print(f"  ${q['total']} ~{q['hours']}h ${q['per_hour']}/hr need {x['need']} {x['source']} {x['kind']}: {x['title']}")


if __name__ == "__main__":
    main()
