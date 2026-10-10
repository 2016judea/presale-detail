"""Deterministic quote per listing: the model's findings -> service tiers (keyword rules),
each priced from data/price_table.json (local median minus config.DISCOUNT, rounded to
$5) or config.PRICE_OVERRIDE, with hours from config.HOURS. No model touches a number."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

TABLE = json.loads((ROOT / "data" / "price_table.json").read_text())["tiers"]

NAMES = {
    "car_interior": "an interior detail", "car_wash_wax": "a wash and wax",
    "car_full": "a full detail inside and out", "paint_correction": "a buff to bring the paint back",
    "headlight": "headlight restoration", "touch_up": "touch-up",
    "boat_wash_wax": "a wash and wax", "boat_oxidation": "compounding the oxidized gelcoat",
}

HEADLIGHT = re.compile(r"headlight", re.I)
PAINT = re.compile(r"\b(dull|flat|faded|oxidi[sz]ed|chalk|swirl|hazy clear|clear ?coat|little (gloss|reflection)|light scratch)", re.I)
INTERIOR = re.compile(r"\b(interior|seat|carpet|upholster|floor ?mat|dash|console|headliner|cabin|cargo|trunk area|footwell|dog hair|pet hair|crumbs|clutter)", re.I)
GRIME = re.compile(r"\b(dirt|dirty|grime|grimy|dust|mud|water ?spot|road film|film|stain|bird|sap|pollen|streak)", re.I)
TOUCH = re.compile(r"\b(chip|touch-?up|paint transfer|scrape)", re.I)
BOAT_OX = re.compile(r"\b(chalk|oxidi[sz]|gelcoat|hull)\w*.*\b(dull|faded|chalk|oxid|cloudy|hazy|flat|blotch)|\b(dull|faded|chalky|oxidi[sz]ed|cloudy|blotchy)\b.*\b(gelcoat|hull|topsides|deck)", re.I)
BOAT_WASH = re.compile(r"\b(dirt|dirty|grime|grimy|stain|scum|mildew|mold|algae|waterline|vinyl|seat|carpet|floor|deck|cockpit|dust|leaves|debris)", re.I)
LENGTH = re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d)?)\s*(?:'|’|′|ft\b|feet\b|foot\b|-foot\b| foot\b)", re.I)


def round5(x):
    return int(x / 5 + 0.5) * 5  # half up: $202.50 -> $205


def unit_price(tier):
    if tier in config.PRICE_OVERRIDE:
        return config.PRICE_OVERRIDE[tier], "your price (config.py)"
    row = TABLE.get(tier)
    if not row or row["median"] is None:
        return None, "no local price found"
    return round5(row["median"] * (1 - config.DISCOUNT)), ("thin: " if row["thin"] else "") + f"local median ${row['median']:g}, n={row['n']}"


def boat_length(l):
    loa = (l.get("attrs") or {}).get("length overall (LOA)")
    if loa and re.match(r"^\d+(\.\d+)?$", loa.strip()):
        return float(loa), "listing"
    for text in (l.get("title", ""), l.get("body", "")):
        for m in LENGTH.finditer(text):
            v = float(m.group(1))
            if 8 <= v <= 60:
                return v, "listing"
    return float(config.BOAT_LENGTH_DEFAULT_FT), "default"


def tiers_for(l, findings):
    f = list(findings)
    t = []
    if l["kind"] == "boat":
        if any(BOAT_OX.search(x) for x in f):
            t.append(("boat_oxidation", 1))
        if any(BOAT_WASH.search(x) for x in f) or not t:
            t.append(("boat_wash_wax", 1))
        return t
    interior = any(INTERIOR.search(x) for x in f)
    grime = any(GRIME.search(x) and not INTERIOR.search(x) for x in f)
    if interior and grime:
        t.append(("car_full", 1))
    elif interior:
        t.append(("car_interior", 1))
    elif grime:
        t.append(("car_full", 1))  # no local wash-only price; a full detail covers it
    if any(PAINT.search(x) and not HEADLIGHT.search(x) and not INTERIOR.search(x) for x in f):
        t.append(("paint_correction", 1))
    if any(HEADLIGHT.search(x) for x in f):
        t.append(("headlight", 1))
    areas = sum(1 for x in f if TOUCH.search(x))
    if areas:
        t.append(("touch_up", min(areas, 2)))
    return t


def quote(l, a):
    lines, total, hours, missing = [], 0, 0.0, []
    length, length_src = (boat_length(l) if l["kind"] == "boat" else (None, None))
    for tier, qty in tiers_for(l, a.get("findings", [])):
        price, basis = unit_price(tier)
        per_ft = tier.startswith("boat_")
        q = length if per_ft else qty
        h = config.HOURS[tier][0] * q
        if price is None:
            missing.append(tier)
            lines.append({"tier": tier, "name": NAMES[tier], "qty": q, "unit_price": None,
                          "amount": None, "hours": round(h, 2), "basis": basis})
            continue
        amt = round5(price * q)
        total += amt
        hours += h
        lines.append({"tier": tier, "name": NAMES[tier], "qty": q, "unit_price": price,
                      "amount": amt, "hours": round(h, 2), "basis": basis})
    return {
        "lines": lines, "total": total or None, "hours": round(hours, 2) or None,
        "per_hour": round(total / hours) if total and hours else None,
        "missing": missing, "boat_length": length, "boat_length_src": length_src,
    }
