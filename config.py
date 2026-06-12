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
LISTINGS = [
    {
        # >>> DUMMY PLACEHOLDER — replace before real use <<<
        "address": "123 Example Ave, Manteca, CA 95336",
        "price": "$675,000",
        "beds": 4,
        "baths": 3,
        "key_features": [
            "Built 2019, low-maintenance yard",
            "Commuter-friendly: minutes to I-205 / Altamont Pass",
            "Open-concept kitchen, owned solar",
        ],
        "status": "active",
        "media_notes": "Have 20 photos + a 45s walkthrough clip. No drone yet.",
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
TARGET_PLATFORMS = ["instagram", "youtube", "linkedin", "x"]

# ---------------------------------------------------------------------------
# 6) Local paths (no cloud, no hosted DB — $0 constraint).
# ---------------------------------------------------------------------------
DB_PATH = "data/content_agent.db"
SEED_CSV_PATH = "seed_posts.csv"
OUTPUT_DIR = "output"
