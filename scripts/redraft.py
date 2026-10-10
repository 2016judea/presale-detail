"""Write each card's opening sentence from the STORED findings (no photos, no vision call).
The rest of the message (upside, quote, next step) is composed in code by build.py,
so the model never writes a number. Cached by listing id + findings hash."""
import concurrent.futures as cf
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import config  # noqa: E402
from assess import client  # noqa: E402

OUT = ROOT / "data" / "openers"
OUT.mkdir(parents=True, exist_ok=True)

SYSTEM = """Write the first sentence of a short text from a local car and boat detailer to \
a private seller. It opens on their listing: say you saw their listing (name the vehicle \
the way a person would, e.g. "the Crown Vic", "your Crownline") and name the one or two \
most visible things from the photo notes that a detail would fix. Plain words a person \
would text. One sentence, under 30 words. No dollar amounts, prices, percentages or \
numbers other than a model year or model number. No em dashes or en dashes. No \
exclamation marks, no emojis, no greeting name. Start with "Hi, " """

BAD = re.compile(r"[$%—–!]|\b(worth|value|price|dollars?)\b", re.I)


def key(l, a):
    return hashlib.md5((l["title"] + "|" + "|".join(a["findings"])).encode()).hexdigest()[:10]


def opener(l, a):
    p = OUT / f"{l['id']}.json"
    k = key(l, a)
    if p.exists():
        rec = json.loads(p.read_text())
        if rec.get("key") == k:
            return rec["text"]
    notes = "\n".join("- " + f for f in a["findings"])
    text = ""
    for _ in range(3):
        r = client.messages.create(
            model=config.MODEL, max_tokens=2000, system=SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": f"Listing title: {l['title']}\nKind: {l['kind']}\nPhoto notes:\n{notes}"}])
        text = next((b.text for b in r.content if b.type == "text"), "").strip().strip('"')
        if text and not BAD.search(text):
            break
        text = ""
    p.write_text(json.dumps({"id": l["id"], "key": k, "text": text}, indent=1))
    return text


def main():
    L = json.loads((ROOT / "data" / "listings.json").read_text())["listings"]
    todo = []
    for l in L:
        ap = ROOT / "data" / "assessments" / f"{l['id']}.json"
        if not ap.exists():
            continue
        a = json.loads(ap.read_text())
        if a.get("fit") and a.get("need_score", 0) >= 4:
            todo.append((l, a))
    print(f"{len(todo)} openers", flush=True)
    with cf.ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda x: opener(*x), todo))
    blank = sum(1 for l, a in todo if not json.loads((OUT / f"{l['id']}.json").read_text())["text"])
    print(f"done, {blank} blank", flush=True)


if __name__ == "__main__":
    main()
