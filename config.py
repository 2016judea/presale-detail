"""One place to change the market. Another city is a one-line change."""

# Craigslist subdomain. Twin Cities by default; "duluth", "stcloud", "rochester",
# "mankato", "fargo" etc. all work the same way.
CITY = "minneapolis"

# How many of the most recently active listings to read per section, per refresh.
MAX_PER_SECTION = 150

# Craigslist category codes (search?cat=X&purveyor=owner). Note the trap: the
# legacy path /search/boo is ALL boats (dealers included); by-owner is
# cat=boo&purveyor=owner, which is what /search/boa redirects to.
SECTIONS = {
    "boat": "boo",
    "car": "cta",
}

# Vision model. Never the source of a dollar figure.
MODEL = "claude-opus-5-5"
PHOTOS_PER_LISTING = 5

# ---- Pricing. The local medians come from data/price_table.json (scripts/price_table.py),
# read off competitors' own ads. Quote = local median minus DISCOUNT, rounded to $5.
DISCOUNT = 0.10

# Set your own price for any tier here and it wins over the computed quote.
# Tiers: car_interior, car_wash_wax, car_full, paint_correction, headlight,
#        touch_up (per area), boat_wash_wax (per ft), boat_oxidation (per ft)
PRICE_OVERRIDE = {
    # "headlight": 60,
}

# When a boat listing states no length, quote this size and say so on the card.
BOAT_LENGTH_DEFAULT_FT = 20

# ---- Hours per tier, for $/hr ranking. Each row says where it came from.
# "stated" rows are durations competitors wrote in their own ads (n and sources in
# data/price_table.json). "default" rows are NOT measurements: a starting guess for
# the brother and Darren to replace with their own times.
HOURS = {
    "car_interior":     (2.5, "default"),
    "car_wash_wax":     (1.5, "default"),
    "car_full":         (4.0, "default"),
    "paint_correction": (5.0, "default"),
    "headlight":        (0.75, "default"),
    "touch_up":         (1.5, "default"),    # per area
    "boat_wash_wax":    (0.1, "default"),    # per foot
    "boat_oxidation":   (0.3, "default"),    # per foot
}
