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

import json

from flask import Flask, jsonify, render_template_string

import config
import db

app = Flask(__name__)


# ---------------------------------------------------------------------------
# JSON APIs (read-only) — the frontend polls these.
# ---------------------------------------------------------------------------
@app.get("/api/summary")
def api_summary():
    with db.get_conn() as conn:
        runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        drafts = conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
        spend = conn.execute(
            "SELECT COALESCE(SUM(est_cost_usd), 0) FROM runs"
        ).fetchone()[0]
    return jsonify(
        runs=runs, posts=posts, drafts=drafts, spend=round(spend or 0, 4),
        market=config.MARKET_LABEL,
    )


@app.get("/api/runs")
def api_runs():
    """Time series: one point per run (chronological)."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT run_id, started_at, posts_collected, "
            "est_cost_usd, est_input_tokens, est_output_tokens "
            "FROM runs ORDER BY started_at ASC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/patterns")
def api_patterns():
    """Latest run's pattern distributions + summary."""
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT run_id, posts_studied, report_json, summary "
            "FROM pattern_reports ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return jsonify(patterns={}, summary="No pattern report yet.",
                       posts_studied=0, run_id=None)
    patterns = json.loads(row["report_json"]).get("patterns", {})
    return jsonify(
        run_id=row["run_id"], posts_studied=row["posts_studied"],
        summary=row["summary"], patterns=patterns,
    )


@app.get("/api/drafts")
def api_drafts():
    """Latest run's drafts, grouped by listing."""
    with db.get_conn() as conn:
        latest = conn.execute(
            "SELECT run_id FROM drafts ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not latest:
            return jsonify(run_id=None, listings={})
        rows = conn.execute(
            "SELECT listing_address, platform, hook, caption, hashtags, "
            "suggested_format, video_outline FROM drafts "
            "WHERE run_id = ? ORDER BY listing_address, platform",
            (latest["run_id"],),
        ).fetchall()
    listings = {}
    for r in rows:
        listings.setdefault(r["listing_address"], []).append(dict(r))
    return jsonify(run_id=latest["run_id"], listings=listings)


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
  const [s, runs, pat, dr] = await Promise.all([
    fetch('/api/summary').then(r=>r.json()),
    fetch('/api/runs').then(r=>r.json()),
    fetch('/api/patterns').then(r=>r.json()),
    fetch('/api/drafts').then(r=>r.json()),
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
    db.init_db()
    print("Dashboard -> http://127.0.0.1:5000  (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=5000, debug=False)
