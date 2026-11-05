"""Ask Gemini (with Google Search grounding) for competitive US detailing rates per tier.
Writes data/ai_prices.json; quote.py uses it for every tier config.PRICE_OVERRIDE doesn't set.
Aidan 2026-10-10: "just ask an AI to price it." Rerun to refresh."""
import json, os, re, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = os.environ.get("GEMINI_API_KEY") or next(
    l.split("=", 1)[1].strip().strip('"') for l in open(Path.home() / "Desktop/workspace/bricks/.env") if l.startswith("GEMINI_API_KEY"))
TIERS = {
    "car_interior": "interior detail, sedan/SUV", "car_wash_wax": "exterior hand wash and wax",
    "car_full": "full detail inside and out, sedan/SUV", "paint_correction": "one-step paint correction / buff and polish",
    "headlight": "headlight restoration, pair", "touch_up": "paint chip/scratch touch-up, per area",
    "boat_wash_wax": "boat wash and wax, PER FOOT", "boat_oxidation": "boat gelcoat oxidation removal (compound, polish, wax), PER FOOT",
}
PROMPT = f"""You are pricing services for a two-person independent MOBILE car and boat detailing side business
in the Minneapolis-Saint Paul metro. Price each service competitively: a little under what typical US
mobile detailers charge, so the quote wins the job. Also give typical job hours for one person.
Services: {json.dumps(TIERS)}
Reply with JSON only: {{"<tier>": {{"price": number, "hours": number, "us_low": number, "us_high": number}}}}.
Per-foot tiers are priced and timed per foot."""

body = {"contents": [{"parts": [{"text": PROMPT}]}], "tools": [{"google_search": {}}]}
req = urllib.request.Request(
    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro-latest:generateContent",
    data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": KEY})
out = json.load(urllib.request.urlopen(req, timeout=180))
text = "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"])
prices = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
missing = set(TIERS) - set(prices)
assert not missing, f"Gemini skipped {missing}"
(ROOT / "data" / "ai_prices.json").write_text(json.dumps(
    {"model": "gemini-pro-latest + google_search", "prices": prices}, indent=2))
for t, r in prices.items():
    print(f"{t:17} ${r['price']:>6}  {r['hours']}h  (US {r['us_low']}-{r['us_high']})")
