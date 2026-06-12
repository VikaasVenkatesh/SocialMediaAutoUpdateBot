"""
Central configuration for the Real Estate Content Agent PoC.

Edit the values in this file BEFORE the first run. Everything here is
plain-Python so it can be imported by any phase module.

HARD CONSTRAINT: this PoC must cost $0 to run beyond tiny Claude API usage
that fits inside free starter credits. See MAX_POSTS_PER_RUN below.
"""

# ---------------------------------------------------------------------------
# 1) Sri's current listings — entered by hand for the PoC.
#    Replace the dummy listing below with 1–2 of Sri's REAL active listings.
# ---------------------------------------------------------------------------
# NOTE: pulled from channelrealestate.com/our-active-listings on 2026-06-12.
# That page is an IDX/MLS search feed (total_listings=6613), so VERIFY these are
# Sri's OWN listings before publishing anything. Only facts shown on the site are
# used below — no amenities are invented. Fill in key_features/media_notes with
# real specifics before a real run.
LISTINGS = [
    {
        "address": "7516 Shady Hollow Dr, Newark, CA 94560",
        "price": "$1,398,000",
        "beds": 5,
        "baths": 2,
        "sqft": 1664,
        "key_features": [
            "5 bedrooms / 2 baths, 1,664 sqft",
            "Newark — central Bay Area, Dumbarton Bridge commuter access",
            "Currently holding open houses",
        ],
        "status": "active",
        "media_notes": "Confirm photo/video assets before drafting visuals.",
        "source_url": "https://www.channelrealestate.com/-/listing/CA-REINFOLINK/ML82050463",
    },
    {
        "address": "39266 Marbella Terraza, Fremont, CA 94538",
        "price": "$749,000",
        "beds": 2,
        "baths": 2,
        "sqft": 1056,
        "key_features": [
            "2 bed / 2 bath condo, 1,056 sqft",
            "Fremont — I-880 / BART-accessible, strong commuter entry point",
            "Currently holding open houses",
        ],
        "status": "active",
        "media_notes": "Confirm photo/video assets before drafting visuals.",
        "source_url": "https://www.channelrealestate.com/-/listing/CA-REINFOLINK/ML82050773",
    },
]

# ---------------------------------------------------------------------------
# 2) Sri's brand brief — the generator MUST match this voice.
# ---------------------------------------------------------------------------
BRAND_BRIEF = (
    "Investor who also brokers. 15 yrs, 500+ transactions. Harvard speaker. "
    "Purpose precedes wealth. Customer-first. Direct, no hype. Signs as Sri."
)

# ---------------------------------------------------------------------------
# 3) Target markets — scopes the YouTube collector's search queries.
#    Sri's niche: fully in the Bay Area, but specializes in the I-580 /
#    Altamont Corridor commuter towns into the Northern San Joaquin Valley.
# ---------------------------------------------------------------------------
TARGET_MARKETS = [
    # Tri-Valley (Bay Area core of the corridor)
    "Pleasanton CA",
    "Livermore CA",
    "Dublin CA",
    "San Ramon CA",
    # Altamont / commuter gateway
    "Tracy CA",
    "Mountain House CA",
    # Northern San Joaquin Valley commuter towns
    "Manteca CA",
    "Lathrop CA",
    "Ripon CA",
    "Stockton CA",
    "Modesto CA",
]

# A short human label used in the digest header.
MARKET_LABEL = "Bay Area + I-580 / Altamont Corridor + N. San Joaquin Valley"

# ---------------------------------------------------------------------------
# 4) Cost guardrails.
# ---------------------------------------------------------------------------
MAX_POSTS_PER_RUN = 200          # hard cap on rows pulled into the analysis
TOP_PERCENT_TO_STUDY = 0.20      # study the top ~20% by engagement

# YouTube collector knobs (free Data API v3 quota is ~10,000 units/day).
YT_RESULTS_PER_MARKET = 10       # videos requested per market search
YT_SEARCH_TERMS = [
    "real estate market update",
    "home tour listing",
    "homes for sale",
]

# ---------------------------------------------------------------------------
# 5) Claude model choices (cheap for analysis, quality for generation).
# ---------------------------------------------------------------------------
ANALYSIS_MODEL = "claude-haiku-4-5-20251001"   # Phase 2: pattern extraction
GENERATION_MODEL = "claude-sonnet-4-6"         # Phase 3: draft generation

# Platforms we want drafts for in Phase 3.
TARGET_PLATFORMS = ["instagram", "youtube", "linkedin", "x", "tiktok", "facebook"]

# ---------------------------------------------------------------------------
# 6) Local paths (no cloud, no hosted DB — $0 constraint).
# ---------------------------------------------------------------------------
DB_PATH = "data/content_agent.db"
SEED_CSV_PATH = "seed_posts.csv"
OUTPUT_DIR = "output"
