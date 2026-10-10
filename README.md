# Pre-Sale Detail

**Live:** https://presale-detail.vercel.app

Every morning: the private sellers in the Twin Cities who just listed a car or boat
on Craigslist, ranked by how much a detail would help their photos. Each card shows
what a vision model saw in the photos (oxidized gelcoat, swirls, a dirty interior,
faded trim), the asking price, how fresh the listing is, and a short message ready
to copy and send.

It's built for a two-person side business that details cars and boats. The person
selling a car is the buyer nobody targets. A pre-sale detail makes it sell faster
and for more, and the listing's clock is already running.

## How it works

1. `scripts/fetch.py` reads the by-owner car and boat sections (curl, ~150 most
   recently active per section) and each posting page.
2. `scripts/assess.py` sends up to 5 photos per listing to Claude, which scores
   detail need 0–10, names what it can see, and drafts the message. Results are
   cached by posting id in `data/assessments/`, so a rerun only pays for new listings.
   The model never produces a dollar figure. Prices come from the listing.
3. `scripts/build.py` ranks by need × price × freshness (boats win ties) and writes
   `site/index.html`.
4. `scripts/deploy.py` pushes `site/` to Vercel.

`./refresh.sh` runs all four. Change `CITY` in `config.py` for another Craigslist market.

Nothing is sent automatically. Craigslist's terms restrict unsolicited service offers,
so reply only where the seller left a phone number or invites contact.

See `DATA_MODEL.md` for the ideal model and which fields the source can't fill.

MIT licensed.
