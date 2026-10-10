"""Look at each listing's photos with a vision model; score detail need, name
what is visible, draft the message. Cached by posting id: a rerun costs $0.

Writes data/assessments/<id>.json (committed, so the cache travels with the repo).
"""
import concurrent.futures as cf
import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

OUT = ROOT / "data" / "assessments"
OUT.mkdir(parents=True, exist_ok=True)

SYSTEM = """You help a two-person side business that details cars and boats: interior \
and exterior detailing, machine buffing / paint correction, gelcoat oxidation removal \
and polish, trim and headlight restoration, and small exterior touch-ups (scuffs, chips, light scratches).

You are shown the photos from a private owner's for-sale listing. Judge, from the photos \
only, how much a pre-sale detail would visibly improve how this vehicle presents to buyers.

Scoring, need_score 0-10:
- 0-2: already clean and glossy, or the photos show nothing a detail would change.
- 3-5: some visible gain (dull paint, dusty interior, light water spots, faded trim).
- 6-8: clear visible gain (oxidized or chalky paint/gelcoat, swirls, stained or cluttered \
interior, grime, waterline scum, faded black trim, scuffs a touch-up fixes).
- 9-10: dramatic: heavy oxidation, filthy interior, chalky hull; the photos are actively \
costing the seller.

Rules:
- Name only things you can actually see, each tied to a place on the vehicle \
("chalky oxidation along the starboard hull", "dog hair on the rear seat"). Never guess \
at what the photos don't show. If photos are too few, dark or distant to judge, say so \
and score low.
- Mechanical damage, rust-through, dents and collision damage are NOT ours to fix. Do not \
list them as findings and do not let them raise the score.
- fit is false when this is not a whole car, truck, SUV, van, motorcycle, boat, PWC or \
pontoon a private owner is selling (parts, trailer-only, engine-only, wanted ads, \
dealer stock, a vehicle we can't detail).
- Never write any dollar amount, price, value, percentage or number of days anywhere. \
Never claim the detail will add a specific amount of money.
- message: 2-4 short sentences a local detailer would text or email the seller. Plain \
words, friendly, no hype, no emojis, no exclamation marks. Say we saw their listing, \
name one or two specific things from the photos, offer a pre-sale detail (or buff / \
gelcoat polish) that comes to them, and ask if they'd like a quote. Do not sign it."""

SCHEMA = {
    "type": "object",
    "properties": {
        "fit": {"type": "boolean"},
        "fit_reason": {"type": "string"},
        "photo_quality": {"type": "string", "enum": ["good", "fair", "poor"]},
        "need_score": {"type": "integer"},
        "findings": {"type": "array", "items": {"type": "string"}},
        "services": {"type": "array", "items": {"type": "string", "enum": [
            "interior detail", "exterior wash and wax", "paint correction / buff",
            "gelcoat oxidation removal", "trim restoration", "headlight restoration", "touch-up"]}},
        "message": {"type": "string"},
    },
    "required": ["fit", "fit_reason", "photo_quality", "need_score", "findings",
                 "services", "message"],
    "additionalProperties": False,
}

MONEY = re.compile(r"\$\s?\d|\d+\s?(?:%|percent|dollars|bucks|k\b)", re.I)


def api_key() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    for env in (ROOT / ".env", Path.home() / "Desktop" / "bricks" / ".env"):
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("no ANTHROPIC_API_KEY")


client = anthropic.Anthropic(api_key=api_key(), max_retries=4)


def describe(l: dict) -> str:
    facts = [f"Section: {l['kind']}s by owner", f"Title: {l['title']}"]
    if l.get("year"):
        facts.append(f"Year: {l['year']}")
    if l.get("make_model"):
        facts.append(f"Make/model: {l['make_model']}")
    for k, v in (l.get("attrs") or {}).items():
        facts.append(f"{k}: {v}")
    facts.append("Seller's text:\n" + (l.get("body") or "")[:1500])
    return "\n".join(facts)


def assess(l: dict) -> dict:
    p = OUT / f"{l['id']}.json"
    if p.exists():
        return json.loads(p.read_text())
    photos = l["photos"][: config.PHOTOS_PER_LISTING]
    if not photos:
        rec = {"id": l["id"], "fit": False, "fit_reason": "no photos", "need_score": 0,
               "findings": [], "services": [], "message": "", "photo_quality": "poor",
               "skipped": True}
        p.write_text(json.dumps(rec, indent=1))
        return rec
    content = [{"type": "image", "source": {"type": "url", "url": u}} for u in photos]
    content.append({"type": "text", "text": describe(l)})
    for attempt in range(2):
        r = client.messages.create(
            model=config.MODEL, max_tokens=4000, system=SYSTEM,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": content}],
        )
        if r.stop_reason == "refusal":
            raise RuntimeError("refusal")
        rec = json.loads(next(b.text for b in r.content if b.type == "text"))
        if not MONEY.search(rec["message"] + " ".join(rec["findings"])):
            break
        content[-1] = {"type": "text", "text": describe(l) + "\n\nYour last answer contained a "
                       "number or dollar figure. Write it again with none."}
    if MONEY.search(rec["message"]):
        rec["message"] = ""  # never ship a model-made number
    rec.update({"id": l["id"], "model": config.MODEL, "photos_seen": len(photos),
                "assessed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "usage": {"in": r.usage.input_tokens, "out": r.usage.output_tokens}})
    p.write_text(json.dumps(rec, indent=1))
    return rec


def main():
    listings = json.loads((ROOT / "data" / "listings.json").read_text())["listings"]
    only = sys.argv[1:]  # optional: ids or a count, for sampling
    if only and only[0].isdigit() and len(only[0]) < 5:
        listings = listings[: int(only[0])]
    elif only:
        listings = [l for l in listings if l["id"] in only]
    todo = [l for l in listings if not (OUT / f"{l['id']}.json").exists()]
    print(f"{len(listings)} listings, {len(todo)} need a model call", flush=True)
    tin = tout = 0
    errors = 0
    with cf.ThreadPoolExecutor(6) as ex:
        futs = {ex.submit(assess, l): l for l in todo}
        for i, f in enumerate(cf.as_completed(futs), 1):
            try:
                u = f.result().get("usage") or {}
                tin += u.get("in", 0)
                tout += u.get("out", 0)
            except Exception as e:
                errors += 1
                print("  fail", futs[f]["id"], e, file=sys.stderr)
            if i % 25 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    cost = tin / 1e6 * 4 + tout / 1e6 * 20  # claude-opus-5-5: $4 in / $20 out per MTok
    summary = {"calls": len(todo) - errors, "errors": errors, "input_tokens": tin,
               "output_tokens": tout, "cost_usd": round(cost, 2)}
    print(json.dumps(summary), flush=True)
    (ROOT / "data" / "last_assess_run.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
