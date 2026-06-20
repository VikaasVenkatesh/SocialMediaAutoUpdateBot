"""
Listings parser for channelrealestate.com (Sri's own IDX site).

Parses the server-rendered AMP listings page into structured listings WITH photo
URLs. Compliant: it's Sri's own site, no auth, light fetch.

IMPORTANT OWNERSHIP NOTE: the public /our-active-listings page is an IDX/MLS
*search feed* of the whole MLS (thousands of listings from many brokerages — each
card credits its real listing broker via "Courtesy of ..."). These are real
properties but NOT necessarily Sri's own listings. Use `courtesy` to filter, and
treat anything not credited to Channel Real Estate as AREA-DEMO data.

Standalone:  python -m listings
"""

import re
import urllib.request

AMP_LISTINGS_URL = "https://www.channelrealestate.com/amp/our-active-listings"
PHOTO_TMPL = ("https://storage.googleapis.com/idx-photos-gs-central.ihouseprd.com/"
              "CA-REINFOLINK/{mls}/org/000.jpg")


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&amp;", "&").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse(html: str) -> list[dict]:
    """Return a list of structured listing dicts parsed from the AMP HTML."""
    listings = []
    # Each card starts at id="ML........"; split on those boundaries.
    starts = [m.start() for m in re.finditer(r'id="(ML\d{8})"', html)]
    ids = re.findall(r'id="(ML\d{8})"', html)
    starts.append(len(html))
    for idx, mls in enumerate(ids):
        block = html[starts[idx]:starts[idx + 1]]
        text = _clean(block)

        price = re.search(r"\$[\d,]{4,}", text)
        beds = re.search(r"(\d+)\s*beds?", text, re.I)
        baths = re.search(r"(\d+(?:\.\d)?)\s*baths?", text, re.I)
        sqft = re.search(r"([\d,]+)\s*sq\s*ft", text, re.I)
        courtesy = re.search(r"Courtesy of ([^|]+?)(?:\s{2,}|$|<)", text)
        # Address: from the listing link slug, which is human-readable.
        slug = re.search(r"/-/listing/CA-REINFOLINK/%s/([^?\"]+)" % mls, block)
        address = None
        if slug:
            address = slug.group(1).replace("-", " ").strip()
        # Photo: prefer the amp-img src, else construct from the template.
        photo = re.search(r'src="(https://storage\.googleapis\.com/idx-photos[^"]+)"',
                          block)
        photo_url = photo.group(1) if photo else PHOTO_TMPL.format(mls=mls)

        listings.append({
            "mls": mls,
            "address": address or "(address unavailable)",
            "price": price.group(0) if price else "",
            "beds": int(beds.group(1)) if beds else None,
            "baths": float(baths.group(1)) if baths else None,
            "sqft": int(sqft.group(1).replace(",", "")) if sqft else None,
            "photo_url": photo_url,
            "courtesy": courtesy.group(1).strip() if courtesy else "",
            "listing_url": (f"https://www.channelrealestate.com/-/listing/"
                            f"CA-REINFOLINK/{mls}/"
                            + (slug.group(1) if slug else "")),
            "is_channel": bool(courtesy and re.search(
                r"channel real estate|gopireddy", courtesy.group(1), re.I)),
        })
    return listings


def fetch_listings(url: str = AMP_LISTINGS_URL) -> list[dict]:
    return parse(_fetch(url))


def save_json(path: str = "data/listings.json") -> str:
    """Fetch + parse + write parsed listings to JSON for the dashboard."""
    import json
    import os
    rows = fetch_listings()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return path


if __name__ == "__main__":
    rows = fetch_listings()
    own = [r for r in rows if r["is_channel"]]
    print(f"Parsed {len(rows)} listings; {len(own)} credited to Channel Real Estate.")
    for r in rows[:5]:
        print(f"  {r['price']:>11} | {r['beds']}bd/{r['baths']}ba | "
              f"{r['address']} | by {r['courtesy'][:30]}")
        print(f"      photo: {r['photo_url'][:80]}")
