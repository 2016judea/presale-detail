#!/bin/zsh
# Daily refresh: read listings, assess new ones (cached by posting id), rebuild, deploy.
# Run by hand or from any scheduler you like. Needs ANTHROPIC_API_KEY and VERCEL_TOKEN
# (both read from ~/Desktop/bricks/.env when unset).
set -e
# Competitor prices change slowly; rebuild them by hand now and then:
#   node scripts/fetch_fb_services.js && python3 scripts/price_table.py
cd "$(dirname "$0")"
set -a; [ -f .env ] && . ./.env; [ -z "$VERCEL_TOKEN" ] && . ~/Desktop/bricks/.env; set +a
node scripts/fetch_fb.js   # Facebook Marketplace, headless and logged out
python3 scripts/fetch.py   # Craigslist, then merges both sources
python3 scripts/ai_prices.py   # Gemini competitive rate + hours per tier
python3 scripts/assess.py
python3 scripts/redraft.py   # first line of each message, from the stored findings
python3 scripts/build.py
python3 scripts/deploy.py
