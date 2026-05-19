"""
new_html_template.py
HTML template string para substituir a função index() em main.py.
Cole este conteúdo dentro da f-string retornada por index().
"""

HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ObituaryWatch</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IM+Fell+English:ital@0;1&family=DM+Mono:wght@400;500&family=Crimson+Pro:ital,wght@0,300;0,400;1,300;1,400&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --ink: #1a1614;
    --ink-mid: #3d3530;
    --ink-muted: #7a6e68;
    --ink-faint: #b4a89e;
    --paper: #f5f0e8;
    --paper-warm: #ede6d8;
    --paper-dark: #cfc5b4;
    --accent: #8b1a1a;
    --accent-soft: #c4524a;
    --font-display: 'IM Fell English', Georgia, serif;
    --font-body: 'Crimson Pro', Georgia, serif;
    --font-mono: 'DM Mono', monospace;
  }}

  body {{
    background: var(--paper);
    color: var(--ink);
    font-family: var(--font-body);
    font-size: 17px;
    line-height: 1.65;
    min-height: 100vh;
  }}

  /* ── Masthead ── */
  .masthead {{
    border-bottom: 3px double var(--ink);
    text-align: center;
    padding: 2rem 2rem 1.5rem;
    background: var(--paper);
  }}
  .masthead::before {{
    content: '';
    display: block;
    border-top: 1px solid var(--ink);
    margin-bottom: 1.5rem;
  }}
  .masthead-eyebrow {{
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.25em;
    text-transform: uppercase;
    color: var(--ink-muted);
    margin-bottom: 0.5rem;
  }}
  .masthead h1 {{
    font-family: var(--font-display);
    font-size: clamp(2.4rem, 6vw, 4rem);
    font-weight: 400;
    letter-spacing: -0.01em;
    line-height: 1.05;
    color: var(--ink);
    margin-bottom: 0.35rem;
  }}
  .masthead-tagline {{
    font-style: italic;
    font-size: 15px;
    color: var(--ink-muted);
    margin-bottom: 1.25rem;
  }}
  .masthead::after {{
    content: '\2014\2009\2736\2009\2014';
    display: block;
    font-family: var(--font-display);
    color: var(--ink-faint);
    font-size: 14px;
    margin-top: 1.25rem;
  }}

  /* ── RSS Banner ── */
  .rss-banner {{
    background: var(--ink);
    color: var(--paper);
    padding: 0.65rem 2rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.06em;
    flex-wrap: wrap;
  }}
  .rss-banner .label {{ color: var(--ink-faint); text-transform: uppercase; }}
  .rss-banner a {{ color: #e8c06a; text-decoration: none; }}
  .rss-banner a:hover {{ text-decoration: underline; }}
  .rss-dot {{
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #e8c06a;
    flex-shrink: 0;
    animation: pulse 2s ease-in-out infinite;
  }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.3}} }}

  /* ── Stats strip ── */
  .stat-strip {{
    background: var(--paper-warm);
    border-top: 1px solid var(--paper-dark);
    border-bottom: 1px solid var(--paper-dark);
    padding: 0.85rem 2rem;
    display: flex;
    gap: 3rem;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.12em;
    color: var(--ink-muted);
    text-transform: uppercase;
  }}
  .stat-strip strong {{
    font-size: 1.1rem;
    font-weight: 400;
    color: var(--ink);
    font-family: var(--font-display);
    display: block;
    margin-bottom: 1px;
  }}

  /* ── Two-column layout ── */
  .layout {{
    max-width: 960px;
    margin: 0 auto;
    padding: 2.5rem 1.5rem 5rem;
    display: grid;
    grid-template-columns: 1fr 1.1fr;
    gap: 0;
  }}
  .col-left {{
    border-right: 1px solid var(--paper-dark);
    padding-right: 2.5rem;
  }}
  .col-right {{ padding-left: 2.5rem; }}

  /* ── Section headers ── */
  .section-head {{
    font-family: var(--font-mono);
    font-size: 9px;
    letter-spacing: 0.3em;
    text-transform: uppercase;
    color: var(--ink-muted);
    border-bottom: 1px solid var(--paper-dark);
    padding-bottom: 0.5rem;
    margin-bottom: 1.25rem;
    margin-top: 2rem;
  }}
  .section-head:first-child {{ margin-top: 0; }}

  /* ── Forms ── */
  .form-group {{
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    margin-bottom: 0.85rem;
  }}
  .form-label {{
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--ink-muted);
  }}
  input[type=text], select {{
    background: var(--paper-warm);
    border: 1px solid var(--paper-dark);
    border-radius: 0;
    padding: 0.5rem 0.75rem;
    font-family: var(--font-body);
    font-size: 15px;
    color: var(--ink);
    width: 100%;
    outline: none;
    transition: border-color 0.15s, background 0.15s;
    -webkit-appearance: none;
    appearance: none;
  }}
  input[type=text]:focus, select:focus {{
    border-color: var(--ink-mid);
    background: #fff;
  }}
  .btn {{
    background: var(--ink);
    color: var(--paper);
    border: none;
    padding: 0.6rem 1.25rem;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background 0.15s;
    border-radius: 0;
    width: 100%;
  }}
  .btn:hover {{ background: var(--accent); }}
  .btn-ghost {{
    background: transparent;
    color: var(--ink-muted);
    border: 1px solid var(--paper-dark);
    padding: 0.2rem 0.5rem;
    font-size: 9px;
    width: auto;
  }}
  .btn-ghost:hover {{ background: var(--accent); color: var(--paper); border-color: var(--accent); }}

  hr.divider {{
    border: none;
    border-top: 1px solid var(--paper-dark);
    margin: 1.75rem 0;
  }}

  /* ── Watchlist ── */
  .watch-list {{ list-style: none; }}
  .watch-item {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.55rem 0;
    border-bottom: 1px solid var(--paper-warm);
    font-size: 15px;
  }}
  .watch-name {{ flex: 1; color: var(--ink); }}
  .watch-cat {{
    font-family: var(--font-mono);
    font-size: 9px;
    letter-spacing: 0.1em;
    color: var(--ink-muted);
    text-transform: uppercase;
    flex-shrink: 0;
  }}

  /* ── Death cards ── */
  .death-card {{
    border-left: 2px solid var(--accent);
    padding: 0.65rem 0 0.65rem 1rem;
    margin-bottom: 1.1rem;
  }}
  .death-name {{
    font-family: var(--font-display);
    font-size: 1.1rem;
    font-weight: 400;
    color: var(--ink);
    text-decoration: none;
    display: block;
    line-height: 1.25;
    margin-bottom: 0.2rem;
    transition: color 0.15s;
  }}
  .death-name:hover {{ color: var(--accent); }}
  .death-meta {{
    font-family: var(--font-mono);
    font-size: 9px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--ink-muted);
  }}
  .death-date {{ color: var(--accent-soft); }}

  .empty-note {{
    font-style: italic;
    color: var(--ink-muted);
    font-size: 15px;
    padding: 0.5rem 0;
  }}

  .bulk-msg {{
    font-style: italic;
    font-size: 13px;
    color: var(--ink-muted);
    margin-top: 0.5rem;
    min-height: 1.2em;
  }}

  @media (max-width: 620px) {{
    .layout {{ grid-template-columns: 1fr; }}
    .col-left {{
      border-right: none;
      padding-right: 0;
      border-bottom: 1px solid var(--paper-dark);
      padding-bottom: 2.5rem;
      margin-bottom: 2rem;
    }}
    .col-right {{ padding-left: 0; }}
    .stat-strip {{ gap: 1.5rem; }}
  }}
</style>
</head>
<body>

<header class="masthead">
  <div class="masthead-eyebrow">Wikipedia &middot; RecentChanges Stream &middot; Zero cost</div>
  <h1>&#128719; ObituaryWatch</h1>
  <div class="masthead-tagline">A quiet vigil over the names that matter to you</div>
</header>

<div class="rss-banner">
  <div class="rss-dot"></div>
  <span class="label">RSS &mdash;</span>
  <a href="{rss_url}">{rss_url}</a>
  <span class="label" style="margin-left:auto;">Feedly &middot; NewsBlur &middot; NetNewsWire &middot; Any reader</span>
</div>

<div class="stat-strip">
  <div><strong>{watched_count}</strong>Watching</div>
  <div><strong>{death_count}</strong>Deaths detected</div>
</div>

<div class="layout">

  <!-- LEFT COLUMN: Forms + Watchlist -->
  <div class="col-left">

    <div class="section-head">Add person</div>
    <div class="form-group">
      <label class="form-label" for="name">Name</label>
      <input type="text" id="name" placeholder="e.g. Paul McCartney" autocomplete="off">
    </div>
    <div class="form-group">
      <label class="form-label" for="cat">Category</label>
      <select id="cat">
        <option value="">&mdash; none &mdash;</option>
        {category_options}
      </select>
    </div>
    <button class="btn" onclick="addPerson()">Add to watchlist</button>

    <hr class="divider">

    <div class="section-head">Add entire category</div>
    <div class="form-group">
      <label class="form-label" for="bulk-cat">Category</label>
      <select id="bulk-cat">{bulk_category_options}</select>
    </div>
    <div class="form-group">
      <label class="form-label" for="bulk-list">List name <em style="font-style:italic;text-transform:none;letter-spacing:0">(optional)</em></label>
      <input type="text" id="bulk-list" placeholder="e.g. my-musicians">
    </div>
    <button class="btn" onclick="addCategory()">Add all living people in category</button>
    <p class="bulk-msg" id="bulk-msg"></p>

    <hr class="divider">

    <div class="section-head">Watchlist &mdash; {watched_count} people</div>
    <ul class="watch-list" id="watch-tbody">
      {watched_rows}
    </ul>

  </div>

  <!-- RIGHT COLUMN: Deaths -->
  <div class="col-right">

    <div class="section-head">Detected deaths &mdash; {death_count}</div>
    <div id="deaths-container">
      {deaths_html}
    </div>

  </div>
</div>

<script>
async function addPerson() {{
  const name = document.getElementById('name').value.trim();
  const cat  = document.getElementById('cat').value;
  if (!name) return alert('Enter a name');
  const r = await fetch('/watch', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ display_name: name, category: cat || null }})
  }});
  const d = await r.json();
  alert(d.message + ': ' + d.display_name);
  location.reload();
}}

async function addCategory() {{
  const cat  = document.getElementById('bulk-cat').value;
  const slug = document.getElementById('bulk-list').value.trim() || null;
  document.getElementById('bulk-msg').textContent = 'Querying Wikidata\u2026 this takes ~10s';
  const r = await fetch('/watch/category', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ category: cat, list_slug: slug, limit: 200 }})
  }});
  const d = await r.json();
  document.getElementById('bulk-msg').textContent =
    'Added ' + d.newly_added + ' people (' + d.already_watching + ' already watched).';
  location.reload();
}}

async function removeWatch(title) {{
  if (!confirm('Remove ' + title.replace(/_/g,' ') + ' from watchlist?')) return;
  await fetch('/watch/' + encodeURIComponent(title), {{ method: 'DELETE' }});
  location.reload();
}}
</script>
</body>
</html>'''
