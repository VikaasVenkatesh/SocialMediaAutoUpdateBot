"""
Local dashboard for the Real Estate Content Agent PoC.

A single-file Flask app that reads the same SQLite DB the pipeline writes
(config.DB_PATH) and visualizes it: runs over time (cost + posts collected),
the latest run's mined pattern distributions, and the generated drafts.

Stays $0 / no-build: Chart.js is loaded from a CDN, data comes straight from
SQLite. Re-run `python main.py` and refresh the page to see updates.

    pip install -r requirements.txt
    python dashboard.py            # -> http://127.0.0.1:5000
"""

import os

from flask import Flask, jsonify, render_template_string, request

import config
import ratelimit
import snapshot

app = Flask(__name__)


def _gen_state():
    """Where/whether generation is allowed.

    - Local: SQLite DB present + Anthropic key  -> enabled, no password.
    - Hosted (Vercel, no DB): Anthropic key env + GENERATE_PASSWORD set
      -> enabled, password required (so strangers can't spend your credits).
    """
    key = os.getenv("ANTHROPIC_API_KEY", "")
    has_key = bool(key) and not key.startswith("your-")
    # On Vercel the filesystem is read-only and VERCEL=1 is set — force the
    # snapshot (no-DB) generation path even if a stray DB file was uploaded.
    on_vercel = bool(os.getenv("VERCEL"))
    has_db = os.path.exists(config.DB_PATH) and not on_vercel
    has_pw = bool(os.getenv("GENERATE_PASSWORD", ""))
    enabled = has_key and (has_db or has_pw)
    # Require a password whenever there's no local DB (i.e. the hosted site).
    requires_password = enabled and (has_pw and not has_db or has_pw)
    return {"enabled": enabled, "requires_password": requires_password,
            "has_db": has_db}


# ---------------------------------------------------------------------------
# JSON APIs (read-only). Source data from the shared snapshot layer: live
# SQLite when running locally, the committed snapshot.json when on Vercel.
# ---------------------------------------------------------------------------
@app.get("/api/summary")
def api_summary():
    return jsonify(snapshot.get_data()["summary"])


@app.get("/api/runs")
def api_runs():
    return jsonify(snapshot.get_data()["runs"])


@app.get("/api/patterns")
def api_patterns():
    return jsonify(snapshot.get_data()["patterns"])


@app.get("/api/drafts")
def api_drafts():
    return jsonify(snapshot.get_data()["drafts"])


@app.get("/api/trends")
def api_trends():
    return jsonify(snapshot.get_data().get("trends", []))


def _parsed_listings():
    """Real listings parsed from Sri's IDX site (committed data/listings.json)."""
    import json
    p = os.path.join(os.path.dirname(__file__), "data", "listings.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


# Platforms where a single image card is the deliverable.
IMAGE_PLATFORMS = ["instagram", "linkedin", "facebook"]


@app.get("/api/image_listings")
def api_image_listings():
    rows = _parsed_listings()
    out = [{
        "index": i,
        "address": r.get("address", ""),
        "price": r.get("price", ""),
        "specs": " · ".join(filter(None, [
            f"{r['beds']} bd" if r.get("beds") else "",
            f"{r['baths']} ba" if r.get("baths") else "",
            f"{r['sqft']:,} sqft" if r.get("sqft") else "",
        ])),
        "courtesy": r.get("courtesy", ""),
        "demo": not r.get("is_channel", False),
    } for i, r in enumerate(rows)]
    return jsonify(listings=out, platforms=IMAGE_PLATFORMS,
                   enabled=bool(rows))


@app.post("/api/generate_image")
def api_generate_image():
    """Render a branded image card from a real listing photo (free, no API)."""
    state = _gen_state()
    body = request.get_json(force=True, silent=True) or {}
    # Same password gate as text generation when hosted.
    if state["requires_password"]:
        supplied = body.get("password") or request.headers.get("X-Gen-Password", "")
        if supplied != os.getenv("GENERATE_PASSWORD", ""):
            return jsonify(error="Invalid or missing password."), 401

    client_ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "?")
                 .split(",")[0].strip())
    ok, retry_after = ratelimit.check_many([
        (f"img:{client_ip}", *config.RATE_LIMIT_PER_IP),
    ])
    if not ok:
        resp = jsonify(error=f"Rate limit reached. Try again in ~{retry_after}s.")
        resp.headers["Retry-After"] = str(retry_after)
        return resp, 429

    rows = _parsed_listings()
    try:
        idx = int(body.get("index", -1))
        listing = rows[idx]
    except (ValueError, IndexError):
        return jsonify(error="Invalid listing."), 400
    platform = body.get("platform", "instagram")

    import base64
    import imagegen
    city = listing.get("address", "").split(" CA")[0].strip()
    png = imagegen.make_card(
        listing, platform,
        hook=f"Just listed in {city}" if city else None,
        demo=not listing.get("is_channel", False),
    )
    uri = "data:image/png;base64," + base64.b64encode(png).decode()
    return jsonify(image=uri, address=listing.get("address", ""),
                   demo=not listing.get("is_channel", False))


@app.get("/api/config")
def api_config():
    """Listings + platforms for the generate controls, and whether it's enabled."""
    state = _gen_state()
    return jsonify(
        listings=[l["address"] for l in config.LISTINGS],
        platforms=config.TARGET_PLATFORMS,
        generation_enabled=state["enabled"],
        requires_password=state["requires_password"],
    )


@app.post("/api/generate")
def api_generate():
    """On-demand single-platform draft generation.

    Local: generates from SQLite + stores. Hosted: generates from the committed
    snapshot's patterns, gated by a password so strangers can't spend credits.
    """
    state = _gen_state()
    if not state["enabled"]:
        return jsonify(error="Generation isn't configured on this deployment."), 403

    body = request.get_json(force=True, silent=True) or {}
    if state["requires_password"]:
        supplied = body.get("password") or request.headers.get("X-Gen-Password", "")
        if supplied != os.getenv("GENERATE_PASSWORD", ""):
            return jsonify(error="Invalid or missing password."), 401

    # Rate limit (defence-in-depth behind the password): per-IP + global/day.
    client_ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "?")
                 .split(",")[0].strip())
    ok, retry_after = ratelimit.check_many([
        (f"ip:{client_ip}", *config.RATE_LIMIT_PER_IP),
        ("global", *config.RATE_LIMIT_GLOBAL),
    ])
    if not ok:
        resp = jsonify(error=f"Rate limit reached. Try again in ~{retry_after}s.")
        resp.headers["Retry-After"] = str(retry_after)
        return resp, 429

    listing = body.get("listing")
    platform = body.get("platform")
    if not listing or not platform:
        return jsonify(error="listing and platform are required."), 400

    if state["has_db"]:
        from phases.p3_apply import generate_one
        draft, err = generate_one(listing, platform)
    else:
        from phases.p3_apply import generate_draft
        pat = snapshot.get_data().get("patterns", {})
        draft, err = generate_draft(listing, platform, pat.get("summary", ""),
                                    pat.get("patterns", {}))
    if err:
        return jsonify(error=err), 400
    # Strip internal fields before returning.
    draft = {k: v for k, v in draft.items() if not k.startswith("_")}
    return jsonify(draft=draft)


# ---------------------------------------------------------------------------
# Single-page frontend.
# ---------------------------------------------------------------------------
PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Content Agent Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root { --bg:#0f1115; --card:#171a21; --line:#262b36; --txt:#e6e9ef;
          --mut:#9aa4b2; --accent:#4f8cff; --accent2:#34d399; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--txt); }
  header { padding:20px 28px; border-bottom:1px solid var(--line);
           display:flex; align-items:baseline; gap:16px; flex-wrap:wrap; }
  header h1 { font-size:18px; margin:0; }
  header .market { color:var(--mut); font-size:13px; }
  header .refresh { margin-left:auto; color:var(--mut); font-size:12px; }
  .wrap { padding:24px 28px; max-width:1200px; margin:0 auto; }
  .cards { display:grid; grid-template-columns:repeat(4,1fr); gap:14px;
           margin-bottom:24px; }
  .card { background:var(--card); border:1px solid var(--line);
          border-radius:12px; padding:16px 18px; }
  .card .k { color:var(--mut); font-size:12px; text-transform:uppercase;
             letter-spacing:.04em; }
  .card .v { font-size:26px; font-weight:650; margin-top:4px; }
  .panel { background:var(--card); border:1px solid var(--line);
           border-radius:12px; padding:18px 20px; margin-bottom:22px; }
  .panel h2 { font-size:14px; margin:0 0 14px; color:var(--mut);
              text-transform:uppercase; letter-spacing:.04em; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:22px; }
  canvas { max-height:260px; }
  .summary { white-space:pre-wrap; color:var(--mut); font-size:13px;
             background:var(--bg); border-radius:8px; padding:12px 14px; }
  details { border:1px solid var(--line); border-radius:8px; margin:8px 0;
            background:var(--bg); }
  details summary { cursor:pointer; padding:10px 14px; font-weight:600; }
  details .body { padding:0 14px 14px; }
  details .body b { color:var(--accent); }
  pre.cap { white-space:pre-wrap; background:var(--card); padding:10px 12px;
            border-radius:6px; font:13px/1.5 inherit; }
  .tag { display:inline-block; background:#222836; color:var(--mut);
         border-radius:5px; padding:1px 7px; font-size:12px; margin-right:4px; }
  .listing-h { font-size:15px; margin:18px 0 6px; color:var(--accent2); }
  .sel { background:var(--bg); color:var(--txt); border:1px solid var(--line);
         border-radius:8px; padding:8px 10px; font:14px inherit; }
  .btn { background:var(--accent); color:#fff; border:none; border-radius:8px;
         padding:9px 16px; font:600 14px inherit; cursor:pointer; }
  .btn:disabled { opacity:.5; cursor:not-allowed; }
  .gen-card { background:var(--bg); border:1px solid var(--accent);
              border-radius:10px; padding:14px 16px; margin-top:14px; }
  @media (max-width:820px){ .cards{grid-template-columns:repeat(2,1fr);}
                            .grid2{grid-template-columns:1fr;} }
</style>
</head>
<body>
<header>
  <h1>🏡 Content Agent Dashboard</h1>
  <span class="market" id="market"></span>
  <span class="refresh">auto-refreshes every 15s · re-run <code>python main.py</code> to update</span>
</header>
<div class="wrap">
  <div class="cards" id="cards"></div>

  <div class="panel">
    <h2>Runs over time</h2>
    <div class="grid2">
      <div><canvas id="costChart"></canvas></div>
      <div><canvas id="postsChart"></canvas></div>
    </div>
  </div>

  <div class="panel">
    <h2>Latest mined patterns <span id="studied" class="market"></span></h2>
    <div class="summary" id="summary"></div>
    <div class="grid2" style="margin-top:16px;">
      <div><canvas id="hookChart"></canvas></div>
      <div><canvas id="topicChart"></canvas></div>
      <div><canvas id="ctaChart"></canvas></div>
      <div><canvas id="hashChart"></canvas></div>
    </div>
  </div>

  <div class="panel">
    <h2>📈 Trending in the niche <span class="market">· Google Trends (California, last 90d)</span></h2>
    <div id="trends"></div>
  </div>

  <div class="panel">
    <h2>✨ Generate a post on demand</h2>
    <div id="genControls" style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
      <select id="genListing" class="sel"></select>
      <select id="genPlatform" class="sel"></select>
      <input id="genPw" class="sel" type="password" placeholder="password"
             style="display:none; width:150px;" autocomplete="off"/>
      <button id="genBtn" class="btn">Generate post</button>
      <span id="genStatus" class="market"></span>
    </div>
    <div id="genResult"></div>
  </div>

  <div class="panel">
    <h2>🖼 Generate an image card <span class="market">· for Instagram / LinkedIn / Facebook (real listing photo + brand)</span></h2>
    <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
      <select id="imgListing" class="sel" style="max-width:340px;"></select>
      <select id="imgPlatform" class="sel"></select>
      <button id="imgBtn" class="btn">Generate image</button>
      <span id="imgStatus" class="market"></span>
    </div>
    <div id="imgResult" style="margin-top:14px;"></div>
  </div>

  <div class="panel">
    <h2>Latest drafts (for review — nothing auto-posts)</h2>
    <div id="drafts"></div>
  </div>
</div>

<script>
const charts = {};
function mk(id, type, labels, data, label, color){
  const el = document.getElementById(id); if(!el) return;
  if(charts[id]) charts[id].destroy();
  charts[id] = new Chart(el, {
    type,
    data:{ labels, datasets:[{ label, data, backgroundColor:color,
            borderColor:color, borderWidth:2, tension:.3, fill:false,
            pointRadius:3 }] },
    options:{ plugins:{legend:{display:false}},
      scales:{ x:{ticks:{color:'#9aa4b2'},grid:{color:'#262b36'}},
               y:{ticks:{color:'#9aa4b2'},grid:{color:'#262b36'},
                  beginAtZero:true} } }
  });
}

async function load(){
  const [s, runs, pat, dr, tr] = await Promise.all([
    fetch('/api/summary').then(r=>r.json()),
    fetch('/api/runs').then(r=>r.json()),
    fetch('/api/patterns').then(r=>r.json()),
    fetch('/api/drafts').then(r=>r.json()),
    fetch('/api/trends').then(r=>r.json()).catch(()=>[]),
  ]);

  document.getElementById('market').textContent = s.market || '';
  document.getElementById('cards').innerHTML = [
    ['Runs', s.runs], ['Posts collected', s.posts],
    ['Drafts generated', s.drafts], ['Est. spend', '$'+s.spend],
  ].map(([k,v])=>`<div class="card"><div class="k">${k}</div>
                   <div class="v">${v}</div></div>`).join('');

  const labels = runs.map((_,i)=>'run '+(i+1));
  mk('costChart','line',labels, runs.map(r=>r.est_cost_usd||0),
     'Est cost ($)', '#4f8cff');
  mk('postsChart','bar',labels, runs.map(r=>r.posts_collected||0),
     'Posts collected', '#34d399');

  document.getElementById('studied').textContent =
    pat.run_id ? `· ${pat.posts_studied} posts studied · ${pat.run_id}` : '';
  document.getElementById('summary').textContent = pat.summary || '';
  const P = pat.patterns || {};
  const dist = f => { const d=(P[f]||{}).distribution||{};
    return [Object.keys(d), Object.values(d)]; };
  const C = '#4f8cff';
  if(P.hook_type){ const [l,d]=dist('hook_type');
    mk('hookChart','bar',l,d,'hook type','#4f8cff'); }
  if(P.topic_category){ const [l,d]=dist('topic_category');
    mk('topicChart','bar',l,d,'topic','#34d399'); }
  if(P.cta_style){ const [l,d]=dist('cta_style');
    mk('ctaChart','bar',l,d,'cta','#f59e0b'); }
  if(P.hashtag_strategy){ const [l,d]=dist('hashtag_strategy');
    mk('hashChart','bar',l,d,'hashtags','#a78bfa'); }

  // trends
  const tbox = document.getElementById('trends');
  if(tbox){
    const rising = (tr||[]).filter(t=>t.kind==='rising').slice(0,12);
    const top = (tr||[]).filter(t=>t.kind==='top').slice(0,12);
    const col = (title,items,color) => `<div><div class="listing-h" style="color:${color}">${title}</div>`
      + (items.length ? items.map(t=>`<span class="tag">${esc(t.query)}`
          + (t.value?` <b style="color:${color}">${t.value>=100?'+'+t.value+'%':t.value}</b>`:'')
          + `</span>`).join(' ')
        : '<span class="market">No data — run the pipeline.</span>') + '</div>';
    tbox.innerHTML = `<div class="grid2">
      ${col('🔥 Rising queries', rising, '#f59e0b')}
      ${col('⭐ Top queries', top, '#34d399')}</div>`;
  }

  // drafts
  const box = document.getElementById('drafts');
  const listings = dr.listings || {};
  if(!Object.keys(listings).length){ box.innerHTML =
    '<div class="summary">No drafts yet. Run the pipeline with an ANTHROPIC_API_KEY set.</div>';
    return; }
  box.innerHTML = Object.entries(listings).map(([addr, items])=>{
    const cards = items.map(d=>`
      <details><summary>${d.platform} — ${d.suggested_format||''}</summary>
        <div class="body">
          <p><b>Hook:</b> ${esc(d.hook)}</p>
          <pre class="cap">${esc(d.caption)}</pre>
          <p>${(d.hashtags||'').split(/\\s+/).filter(Boolean)
                .map(h=>`<span class="tag">${esc(h)}</span>`).join('')}</p>
          <p><b>Video outline:</b></p>
          <pre class="cap">${esc(d.video_outline||'(none)')}</pre>
        </div></details>`).join('');
    return `<div class="listing-h">🏠 ${esc(addr)}</div>${cards}`;
  }).join('');
}
function esc(s){ return (s||'').replace(/[&<>]/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

async function initGen(){
  const cfg = await fetch('/api/config').then(r=>r.json());
  const lSel = document.getElementById('genListing');
  const pSel = document.getElementById('genPlatform');
  lSel.innerHTML = cfg.listings.map(a=>`<option>${esc(a)}</option>`).join('');
  pSel.innerHTML = cfg.platforms.map(p=>`<option>${esc(p)}</option>`).join('');
  const btn = document.getElementById('genBtn');
  const status = document.getElementById('genStatus');
  const pwField = document.getElementById('genPw');
  if(!cfg.generation_enabled){
    btn.disabled = true;
    status.textContent = 'Generation is not configured on this deployment.';
    return;
  }
  if(cfg.requires_password){
    pwField.style.display = '';
    pwField.value = localStorage.getItem('genPw') || '';
    status.textContent = 'Enter the password to generate.';
  }
  btn.onclick = async () => {
    btn.disabled = true; status.textContent = 'Generating…';
    if(cfg.requires_password) localStorage.setItem('genPw', pwField.value);
    try {
      const res = await fetch('/api/generate', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ listing:lSel.value, platform:pSel.value,
                               password: pwField.value })
      }).then(r=>r.json());
      if(res.error){ status.textContent = '⚠ '+res.error; }
      else {
        const d = res.draft;
        status.textContent = `Done · ~$${d.est_cost}`;
        document.getElementById('genResult').innerHTML = `
          <div class="gen-card">
            <div class="listing-h">🏠 ${esc(d.listing_address)} · <b>${esc(d.platform)}</b>
              <span class="tag">${esc(d.suggested_format)}</span></div>
            <p><b>Hook:</b> ${esc(d.hook)}</p>
            <pre class="cap">${esc(d.caption)}</pre>
            <p>${(d.hashtags||'').split(/\\s+/).filter(Boolean)
                  .map(h=>`<span class="tag">${esc(h)}</span>`).join('')}</p>
            <p><b>Video outline:</b></p>
            <pre class="cap">${esc(d.video_outline||'(none)')}</pre>
          </div>`;
        load();  // refresh the latest-drafts list + cards
      }
    } catch(e){ status.textContent = '⚠ '+e; }
    btn.disabled = false;
  };
}

async function initImg(){
  const cfg = await fetch('/api/image_listings').then(r=>r.json());
  const lSel = document.getElementById('imgListing');
  const pSel = document.getElementById('imgPlatform');
  const btn = document.getElementById('imgBtn');
  const status = document.getElementById('imgStatus');
  if(!cfg.enabled){
    btn.disabled = true;
    status.textContent = 'No parsed listings yet (run: python -m listings).';
    return;
  }
  lSel.innerHTML = cfg.listings.map(l=>
    `<option value="${l.index}">${esc(l.address)} — ${esc(l.price)}${l.demo?' [DEMO]':''}</option>`).join('');
  pSel.innerHTML = cfg.platforms.map(p=>`<option>${esc(p)}</option>`).join('');
  const genCfg = await fetch('/api/config').then(r=>r.json());
  btn.onclick = async () => {
    btn.disabled = true; status.textContent = 'Rendering…';
    try {
      const res = await fetch('/api/generate_image', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ index:Number(lSel.value), platform:pSel.value,
          password: (document.getElementById('genPw')||{}).value || '' })
      }).then(r=>r.json());
      if(res.error){ status.textContent = '⚠ '+res.error; }
      else {
        status.textContent = 'Done' + (res.demo?' · AREA DEMO (not Sri\\'s listing)':'');
        document.getElementById('imgResult').innerHTML =
          `<img src="${res.image}" alt="card" style="max-width:420px;border:1px solid var(--line);border-radius:10px;"/>
           <div class="market" style="margin-top:6px;">Right-click → Save image. ${esc(res.address)}</div>`;
      }
    } catch(e){ status.textContent = '⚠ '+e; }
    btn.disabled = false;
  };
}

initGen();
initImg();
load();
setInterval(load, 15000);
</script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(PAGE)


if __name__ == "__main__":
    # Default to 5050 — macOS AirPlay Receiver squats on 5000. Override with PORT.
    port = int(os.getenv("PORT", "5050"))
    print(f"Dashboard -> http://127.0.0.1:{port}  (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=port, debug=False)
