# Real Estate Content Agent — FREE PoC

A zero-cost proof of concept for **Channel Real Estate (Sri Gopireddy)**. In one
manual run it: **collects** recent top-performing real estate content from free
sources, **studies** why it performs, **applies** those patterns to Sri's current
listings to produce approval-ready drafts, **compares** against the prior run,
and writes a **markdown digest** for review.

The point of the PoC is to validate that the generated drafts are genuinely good
and on-brand — **not** to operate at scale. The agent only **drafts**; a human
(Sri) approves and posts. No auto-publishing.

**Niche / target markets:** Bay Area + the I-580 / Altamont Corridor commuter
towns into the Northern San Joaquin Valley (Pleasanton, Livermore, Dublin, San
Ramon, Tracy, Mountain House, Manteca, Lathrop, Ripon, Stockton, Modesto).

---

## Hard constraint: $0

- No paid APIs, no hosted database, no paid scraping, no cloud deploy.
- Storage is a local **SQLite** file (`data/content_agent.db`).
- Output is a local markdown file (`output/digest_<date>.md`).
- Run is triggered **manually** (`python main.py`). No scheduler yet.
- Claude usage stays tiny (capped at `MAX_POSTS_PER_RUN`, batched, Haiku for
  analysis / Sonnet only for generation). Estimated token spend is logged each run.

---

## Free data sources only

1. **YouTube** — fully automated via the **YouTube Data API v3** (free daily
   quota). Searches real-estate keywords scoped to the target markets and pulls
   video metadata + statistics.
2. **X / Instagram / LinkedIn** — **manual seed file**, `seed_posts.csv`. We do
   **not** scrape these (cost + ToS risk). The user pastes public post text by
   hand; the agent treats those rows as collected data.
3. **Sri's own accounts** — optional, free. The Meta Graph API is free for his
   own content + insights. Left as an optional adapter; the PoC works without it.

---

## Project layout

```
SocialMediaAutoUpdateBot/
├── main.py              # runs phases 1→5 in order
├── config.py            # EDIT THIS: listings, brand brief, markets, caps, models
├── db.py                # SQLite schema + helpers (posts, pattern_reports, drafts, runs)
├── seed_posts.csv       # manual X/IG/LinkedIn rows (3 dummy rows included)
├── requirements.txt
├── .env.example         # copy to .env, add API keys
├── phases/
│   ├── p1_collect.py    # Phase 1 — Collect  (YouTube API + CSV → posts)
│   ├── p2_study.py      # Phase 2 — Study    (top ~20% → Claude/Haiku → pattern report)
│   ├── p3_apply.py      # Phase 3 — Apply    (listings → Claude/Sonnet → drafts)
│   ├── p4_compare.py    # Phase 4 — Compare  (diff vs previous run)
│   └── p5_report.py     # Phase 5 — Report   (write digest_<date>.md)
├── data/                # SQLite db lives here (gitignored)
└── output/              # digests written here (gitignored)
```

> **Deliverable 1 status:** scaffold, SQLite schema, `.env.example`, and a sample
> `seed_posts.csv` are complete. Phases 1–5 are wired in `main.py` but their
> bodies are stubs (raise `NotImplementedError`) until deliverables 2–5.

---

## Setup

```bash
cd SocialMediaAutoUpdateBot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then add your real keys
python db.py                # initialize the SQLite schema
```

Get the free keys:
- **YOUTUBE_API_KEY** — Google Cloud Console → enable *YouTube Data API v3* → Credentials → API key.
- **ANTHROPIC_API_KEY** — Anthropic Console → Settings → API Keys (free starter credits cover this PoC).

---

## How to fill `seed_posts.csv`

Browse X / Instagram / LinkedIn for strong real-estate posts in Sri's markets.
For each, add one row (open the file in any spreadsheet app):

| column | meaning |
|---|---|
| `platform` | `instagram` \| `x` \| `linkedin` |
| `post_url` | public link to the post |
| `author` | handle or name |
| `caption_text` | copy the public caption text by hand |
| `likes` | integer |
| `comments` | integer |
| `shares_or_saves` | integer (shares or saves, whichever the platform shows) |
| `format` | `short` \| `long` \| `image` \| `carousel` \| `text` |

Three clearly-labeled **dummy** rows ship in the file — replace them with real
finds before a meaningful run.

---

## How to run

```bash
python main.py
```

Runs Collect → Study → Apply → Compare → Report and prints the digest path plus
estimated token spend. Each phase is also runnable standalone for debugging:

```bash
python -m phases.p1_collect
python -m phases.p2_study
```

---

## Expected token cost

Pennies per run. Analysis uses **Haiku** on the top ~20% of at most
`MAX_POSTS_PER_RUN` (200) posts in batched calls; generation uses **Sonnet** only
for the handful of listing drafts. Each run logs estimated input/output tokens
and a dollar estimate to the `runs` table and prints it at the end.

---

## ⬆️ Upgrade path (documented, not built)

Graduating from PoC to production:

- **Storage:** swap local SQLite → hosted Postgres (Supabase / Neon free tier).
- **Scheduling:** add a GitHub Actions weekly cron to run the loop automatically.
- **Discovery:** replace the manual `seed_posts.csv` with a **licensed** provider
  (Apify / Bright Data) for automated competitor monitoring. **Requires a ToS
  review and a paid/licensed plan** before adding — the PoC deliberately avoids
  scraping X/IG/LinkedIn.
- **Feedback loop:** wire up Sri's own account analytics (Meta Graph API, etc.) so
  posted-content performance feeds back into the pattern report — closing the loop
  Phase 4 only seeds today.
- **Approval + publishing:** add a review/approval step and a publishing
  integration so approved drafts post on a schedule.

---

## Guardrails

- **Human in the loop:** the agent only drafts; nothing is posted automatically.
- **Compliance:** no scraping of X/Instagram/LinkedIn in the PoC — manual seed
  file only. Automated competitor discovery requires paid/licensed providers and
  a ToS review first.
- **Cost:** `MAX_POSTS_PER_RUN` enforced, Claude calls batched, Haiku for
  analysis / Sonnet only for generation, estimated spend printed each run.
