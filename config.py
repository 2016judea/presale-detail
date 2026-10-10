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
