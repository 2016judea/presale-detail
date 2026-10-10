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

# ---- Pricing. Default is Gemini's competitive US rate per tier (scripts/ai_prices.py,
# data/ai_prices.json).

# Set your own price for any tier here and it wins over the computed quote.
# Tiers: car_interior, car_wash_wax, car_full, paint_correction, headlight,
#        touch_up (per area), boat_wash_wax (per ft), boat_oxidation (per ft)
PRICE_OVERRIDE = {
    # "headlight": 60,
}

# When a boat listing states no length, quote this size and say so on the card.
BOAT_LENGTH_DEFAULT_FT = 20

# ---- Hours per tier, for $/hr ranking. Default is Gemini's estimate (data/ai_prices.json).
# Set your own real job times here and they win.
HOURS_OVERRIDE = {
    # "car_full": 3.5,
}
