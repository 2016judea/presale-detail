# Data model — the ideal version

Written 2026-10-10 from the need alone, before looking at any listing data
(~/.claude/BUSINESS.md rule 5). Reality is checked against it at the bottom.

**The need.** Two guys detail cars and boats on the side. The buyer nobody
targets: a private owner who has *just* listed a vehicle for sale. A pre-sale
detail, buff or gelcoat polish makes it sell faster and for more. The tool's job
is to tell them, each morning, *who to offer it to, what to point at, and what to
say* — and to have done the looking for them.

## Entities

### Listing — one vehicle a private owner is trying to sell
| field | question it answers |
|---|---|
| id | Have we seen this one already? (dedupe, cache key) |
| source / url | Where do I go to read it and reply? |
| kind (car / truck / boat / other) | Is this our kind of job, and which service? |
| title | What is it, at a glance? |
| year, make, model | How old / what class — older paint oxidises, older boats chalk |
| length_ft (boats) | How big is the job (gelcoat priced by the foot)? |
| asking_price | How much money is riding on presentation? |
| posted_at | How fresh is it — is the seller's clock still running? |
| updated_at / relisted | Has it sat unsold (repost = urgency up)? |
| price_history | Did they drop the price (urgency up, presentation is a cheaper lever)? |
| location (text + lat/lon) | Can we drive there? How far? |
| body_text | What does the seller say about condition? |
| photos[] | What does it actually look like? |
| seller_contact (phone / email relay / reply-ok flag) | May we reply, and how? |
| seller_says_no_solicitation | Did they ask not to be contacted by services? |
| seller_type (owner / dealer) | Private owner? (dealers have their own detailers) |
| days_until_expiry | How long is the window? |

### Assessment — what a vision model saw in the photos
| field | question it answers |
|---|---|
| listing_id | Joins to Listing |
| need_score 0–10 | How much would a detail visibly help? |
| findings[] (area, issue, photo index) | What exactly do we point at? (swirls on hood, oxidised gelcoat at waterline, stained seats) |
| services[] (interior, exterior wash/wax, paint correction/buff, gelcoat, trim restore, touch-up) | Which of our services fits? |
| photo_quality | Can we even judge from these photos? |
| draft_message | What do we send? |
| model, assessed_at | Is this cached / which model said it? |

### Operator state — the guys' own pipeline (per listing)
| field | question it answers |
|---|---|
| status (new / contacted / replied / booked / passed) | What have we already done? |
| contacted_at, outcome, job_price | Is this working? (their own numbers, never a model's) |

### Service area — one row
| field | question it answers |
|---|---|
| home base (lat/lon), max_drive_miles | Which listings are in range? |
| craigslist subdomain | Which city's market? |

## Joins
Listing 1—1 Assessment (by id). Listing 1—1 Operator state. Service area filters Listing by distance.

## Ranking
opportunity = need_score × f(asking_price) × freshness × (boat bump on ties).
Value asymmetry = need_score × price; obscurity = by-owner Craigslist (no one
targets it); urgency = freshness / repost / price drop; access = they can show up
with a buffer this week. No model-generated dollar figure anywhere.

---

## Reality check (2026-10-10, Craigslist Minneapolis, 300 listings read)

**Filled.** id, url, kind, title, asking_price, posted_at, updated_at (and so
relisted: 198/300 had been renewed), location text and lat/lon (300/300), body,
photos (288/300 have at least one), car year + make/model (150/150), boat length
(150/150), boat year (76/150). Every Assessment field is filled by the vision
model from the photos.

**Can't be filled from the source:**
- `seller_contact.phone`: Craigslist strips phone numbers out of the body text
  (0/300 in plain text). 40/300 have a "show contact info" link that reveals one
  behind a click and a challenge we don't automate. The page flags those posts,
  and the guys tap through on the listing.
- `price_history`: not published. Only 3 titles say "price drop". It can be built
  by keeping each day's snapshot and diffing (not done yet).
- `days_until_expiry`: not published.
- `seller_type`: the by-owner filter is the only signal, and dealers sometimes post
  there anyway. The model flags obvious dealer stock as `fit: false`.
- `seller_says_no_solicitation`: the field is parsed, but 0/300 posts carry it.

**Not built yet (no source problem, just the next slice):** Operator state
(contacted / booked / passed) needs a small store. Service area needs to know
where the guys live, and `config.CITY` is the stand-in until then.

**Call: build.** The fields the thesis rests on (photos → need, price, freshness,
a way to reach the seller) all fill. The gaps cost precision, not the product.
