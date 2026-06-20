"""
Image-card generator for image-first platforms (Instagram, LinkedIn, Facebook).

Builds a branded social graphic from the listing's REAL photo + a text overlay
(price, beds/baths/sqft, address, Sri's brand strip). Free — Pillow only, no API,
no AI hallucination of fake houses. Returns PNG bytes (so it works both locally
and on serverless without writing to disk).

If the photo can't be fetched, falls back to a clean gradient background so a
card is still produced.
"""

import io
import urllib.request

from PIL import Image, ImageDraw, ImageFont

# Platform canvas sizes (px).
SIZES = {
    "instagram": (1080, 1080),
    "facebook": (1200, 630),
    "linkedin": (1200, 627),
    "default": (1080, 1080),
}

BRAND = "Sri Gopireddy · Channel Real Estate"
_FONT_DIR = "/System/Library/Fonts/Supplemental/"


def _font(name, size):
    for path in (f"{_FONT_DIR}{name}", name):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fetch_image(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return Image.open(io.BytesIO(r.read())).convert("RGB")
    except Exception:
        return None


def _cover(img: Image.Image, size) -> Image.Image:
    """Resize+crop to fill `size` (object-fit: cover)."""
    tw, th = size
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    img = img.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
    iw, ih = img.size
    left, top = (iw - tw) // 2, (ih - th) // 2
    return img.crop((left, top, left + tw, top + th))


def _gradient(size, height_frac=0.55):
    """Bottom-up dark gradient for text legibility."""
    w, h = size
    grad = Image.new("L", (1, h), 0)
    start = int(h * (1 - height_frac))
    for y in range(start, h):
        t = (y - start) / max(h - start, 1)
        grad.putpixel((0, y), int(225 * (t ** 1.3)))
    alpha = grad.resize((w, h))
    overlay = Image.new("RGBA", (w, h), (8, 12, 20, 0))
    overlay.putalpha(alpha)
    return overlay


def make_card(listing: dict, platform: str = "instagram",
              hook: str | None = None, demo: bool = False) -> bytes:
    """Render a branded listing card. Returns PNG bytes."""
    size = SIZES.get(platform, SIZES["default"])
    w, h = size

    photo = _fetch_image(listing.get("photo_url", "")) if listing.get("photo_url") else None
    if photo is not None:
        base = _cover(photo, size)
    else:  # gradient fallback
        base = Image.new("RGB", size, (17, 26, 43))
    base = base.convert("RGBA")
    base.alpha_composite(_gradient(size))
    d = ImageDraw.Draw(base)

    pad = int(w * 0.055)
    accent = (255, 255, 255)
    blue = (79, 140, 255)

    # Brand strip (top-left pill).
    bf = _font("Arial Bold.ttf", int(h * 0.026))
    bt = BRAND
    tb = d.textbbox((0, 0), bt, font=bf)
    bw, bh = tb[2] - tb[0], tb[3] - tb[1]
    d.rounded_rectangle([pad, pad, pad + bw + 36, pad + bh + 26], radius=14,
                        fill=(10, 14, 22, 200))
    d.text((pad + 18, pad + 10), bt, font=bf, fill=accent)

    # Optional DEMO badge (top-right) so area listings can't be mistaken as Sri's.
    if demo:
        df = _font("Arial Bold.ttf", int(h * 0.024))
        dt = "AREA DEMO"
        dtb = d.textbbox((0, 0), dt, font=df)
        dw = dtb[2] - dtb[0]
        d.rounded_rectangle([w - pad - dw - 32, pad, w - pad, pad + dtb[3] - dtb[1] + 24],
                            radius=12, fill=(200, 60, 60, 220))
        d.text((w - pad - dw - 16, pad + 8), dt, font=df, fill=accent)

    # Bottom block: price, specs, address, optional hook.
    y = h - pad
    af = _font("Arial.ttf", int(h * 0.030))
    sf = _font("Arial Bold.ttf", int(h * 0.034))
    pf = _font("Arial Black.ttf", int(h * 0.072))

    address = listing.get("address", "")
    specs = " · ".join(filter(None, [
        f"{listing['beds']} bd" if listing.get("beds") else "",
        f"{listing['baths']} ba" if listing.get("baths") else "",
        f"{listing['sqft']:,} sqft" if listing.get("sqft") else "",
    ]))
    price = listing.get("price", "")

    def line(text, font, fill, gap):
        nonlocal y
        if not text:
            return
        bb = d.textbbox((0, 0), text, font=font)
        y -= (bb[3] - bb[1]) + gap
        d.text((pad, y), text, font=font, fill=fill)

    line(address, af, accent, int(h * 0.012))
    line(specs, sf, blue, int(h * 0.018))
    line(price, pf, accent, int(h * 0.010))
    if hook:
        hook = (hook[:70] + "…") if len(hook) > 71 else hook
        line(hook, af, (220, 226, 235), int(h * 0.03))

    out = io.BytesIO()
    base.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


if __name__ == "__main__":
    import listings
    rows = listings.fetch_listings()
    sample = rows[2]  # a real listing with full data
    for plat in ("instagram", "linkedin"):
        png = make_card(sample, plat, hook="Just listed in " + sample["address"].split(" CA")[0],
                        demo=True)
        path = f"output/card_{plat}.png"
        import os
        os.makedirs("output", exist_ok=True)
        with open(path, "wb") as f:
            f.write(png)
        print(f"wrote {path} ({len(png)//1024} KB)")
