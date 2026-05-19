"""
results.py — Search results page (/results?q=Nicolas)

Standalone page, not yet wired to main navigation.
State: watchlist stored in localStorage on the browser side,
synced to the server DB on every add/remove click.

When email service is implemented, it reads from the same DB table.
"""

RESULTS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ObituaryWatch — results</title>
<link href="https://fonts.googleapis.com/css2?family=Special+Elite&family=Courier+Prime:wght@300;400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/static/style.css">
<style>
.results-wrap { max-width: 780px; margin: 0 auto; padding: 40px 24px 80px; }

.top-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 48px; }
.back-btn {
  background: none; border: 1px solid rgba(255,255,255,0.1);
  border-radius: 50px; color: rgba(255,255,255,0.4);
  font-family: "Courier Prime", monospace; font-size: 12px;
  letter-spacing: 0.15em; text-transform: uppercase;
  padding: 8px 16px; cursor: pointer;
  transition: border-color .2s, color .2s;
  white-space: nowrap; flex-shrink: 0;
  text-decoration: none; display: inline-flex; align-items: center; gap: 6px;
}
.back-btn:hover { border-color: rgba(255,255,255,0.4); color: rgba(255,255,255,0.9); }

.search-bar {
  flex: 1; background: #0a0806; border: 1px solid #2a2520;
  color: #e8e4dc; font-family: "Courier Prime", monospace; font-size: 15px;
  padding: 12px 20px; border-radius: 50px; outline: none;
  transition: border-color .2s;
}
.search-bar:focus { border-color: #5a5048; }
.search-bar::placeholder { color: #3a3630; }

.search-go {
  background: transparent; border: 1px solid #4a4038;
  color: #9a8e80; font-family: "Courier Prime", monospace;
  font-size: 13px; padding: 12px 20px; border-radius: 50px;
  cursor: pointer; transition: border-color .15s, color .15s;
  white-space: nowrap; flex-shrink: 0;
}
.search-go:hover { border-color: #7a6a58; color: #f0ece4; }

.result-meta-line {
  font-size: 10px; letter-spacing: 0.25em; text-transform: uppercase;
  color: #5a5650; margin-bottom: 20px;
  font-family: "Special Elite", cursive;
}

.result-list { display: flex; flex-direction: column; gap: 8px; }

.result-row {
  display: flex; align-items: center; gap: 14px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 50px; padding: 10px 18px 10px 10px;
  background: #000; cursor: pointer;
  transition: background .25s, border-color .25s, transform .12s;
  animation: slideIn .4s ease both;
}
.result-row:hover { background: rgba(255,255,255,0.04); border-color: rgba(255,255,255,0.22); transform: scale(1.01); }
.result-row:active { transform: scale(0.99); }
@keyframes slideIn { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }

.r-avatar {
  width: 40px; height: 40px; border-radius: 50%;
  background: #1a1710; border: 1px solid #2a2520;
  flex-shrink: 0; overflow: hidden;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 700; color: #6a6058;
}
.r-avatar img { width: 100%; height: 100%; object-fit: cover; }

.r-info { flex: 1; min-width: 0; }
.r-name { font-size: 14px; color: rgba(255,255,255,0.9); font-weight: 400; letter-spacing: 0.03em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.r-meta { font-size: 11px; color: #5a5650; margin-top: 2px; letter-spacing: 0.04em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.add-btn {
  width: 30px; height: 30px; border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.15);
  background: transparent; color: rgba(255,255,255,0.35);
  font-size: 18px; cursor: pointer; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  transition: border-color .2s, color .2s, background .2s;
  font-family: "Courier Prime", monospace; line-height: 1;
}
.add-btn:hover { border-color: rgba(255,255,255,0.5); color: #fff; background: rgba(255,255,255,0.07); }
.add-btn.added { border-color: #2a4a28; color: #4a7a48; background: #0a120a; }
.add-btn.loading { opacity: 0.4; pointer-events: none; }

.pagination { display: flex; align-items: center; justify-content: center; gap: 6px; margin-top: 48px; }
.page-btn {
  width: 34px; height: 34px; border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.1);
  background: transparent; color: rgba(255,255,255,0.35);
  font-family: "Courier Prime", monospace; font-size: 12px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all .2s;
}
.page-btn:hover { border-color: rgba(255,255,255,0.4); color: rgba(255,255,255,0.9); }
.page-btn.active { border-color: rgba(255,255,255,0.55); color: #fff; background: rgba(255,255,255,0.07); pointer-events: none; }
.page-dots { color: #3a3630; font-size: 12px; padding: 0 2px; }

.no-results { text-align: center; padding: 60px 20px; color: #5a5650; font-style: italic; font-size: 14px; }

@media (max-width: 600px) {
  .top-bar { flex-wrap: wrap; }
  .search-bar { min-width: 0; }
}
</style>
</head>
<body>
<div class="results-wrap">

  <div class="top-bar">
    <a class="back-btn" href="/">&#8592; back</a>
    <input class="search-bar" id="search-bar" type="text" placeholder="search another name..." autocomplete="off" spellcheck="false">
    <button class="search-go" onclick="goSearch()">search</button>
  </div>

  <div class="result-meta-line" id="meta-line">searching...</div>
  <div class="result-list" id="result-list"></div>
  <div class="pagination" id="pagination"></div>

</div>
<script>
const PER_PAGE = 8;
let allResults = [];
let currentPage = 1;
// In-memory watchlist — persists across searches in this session
// On page load we sync from the server so it matches the DB
const watchedTitles = new Set();

async function init() {
  // Load existing watchlist from server to keep + buttons in sync
  try {
    const data = await (await fetch('/watched')).json();
    data.forEach(p => watchedTitles.add(p.wiki_title));
  } catch(e) {}

  // Get query from URL
  const q = new URLSearchParams(location.search).get('q') || '';
  document.getElementById('search-bar').value = q;
  if (q.trim().length >= 2) {
    await runSearch(q.trim());
  } else {
    document.getElementById('meta-line').textContent = 'enter a name to search.';
  }
}

function goSearch() {
  const q = document.getElementById('search-bar').value.trim();
  if (!q) return;
  history.pushState({}, '', '/results?q=' + encodeURIComponent(q));
  currentPage = 1;
  runSearch(q);
}

document.getElementById('search-bar').addEventListener('keydown', e => {
  if (e.key === 'Enter') goSearch();
});

async function runSearch(q) {
  document.getElementById('meta-line').textContent = 'searching...';
  document.getElementById('result-list').innerHTML = '';
  document.getElementById('pagination').innerHTML = '';

  try {
    // Wikipedia opensearch — ranked by popularity
    const wpUrl = 'https://en.wikipedia.org/w/api.php?action=opensearch' +
      '&search=' + encodeURIComponent(q) +
      '&limit=50&namespace=0&format=json&origin=*';
    const [, titles, descs, urls] = await (await fetch(wpUrl)).json();

    const rejectKw = [
      'film','album','song','discography','filmography','soundtrack',
      'television series','tv series','video game','software','web series',
      'municipality','commune','district','river','lake','mountain','building',
      'male given name','female given name','given name','family name','surname'
    ];

    allResults = titles
      .map((t, i) => ({
        title:        t.replace(/ /g, '_'),
        display_name: t,
        description:  descs[i] || '',
        url:          urls[i],
        birth_year:   extractBirthYear(descs[i] || ''),
      }))
      .filter(r => {
        const d = r.description.toLowerCase();
        // Must have a description
        if (!r.description || r.description.trim() === '') return false;
        if (rejectKw.some(kw => d.includes(kw))) return false;
        // Filter people with death year ranges like (1865-1918) or 1947-2022
        if (/\d{4}[\u2013\-]\d{4}/.test(r.description)) return false;
        return true;
      });

    if (!allResults.length) {
      document.getElementById('meta-line').textContent = 'no results for "' + q + '".';
      return;
    }

    renderPage(1, q);

    // Async: fetch thumbnails for current page
    loadThumbnails(allResults.slice(0, PER_PAGE).map(r => r.title));

  } catch(e) {
    document.getElementById('meta-line').textContent = 'error searching. try again.';
  }
}

function extractBirthYear(text) {
  const m = text.match(/born\\s+(\\d{4})|\\(born\\s+(\\d{4})/);
  return m ? parseInt(m[1]||m[2]) : null;
}

function renderPage(page, q) {
  currentPage = page;
  const q_ = q || new URLSearchParams(location.search).get('q') || '';
  const total = allResults.length;
  const totalPages = Math.ceil(total / PER_PAGE);
  const start = (page - 1) * PER_PAGE;
  const pageItems = allResults.slice(start, start + PER_PAGE);

  document.getElementById('meta-line').textContent =
    total + ' result' + (total !== 1 ? 's' : '') + ' for "' + q_ + '"';

  document.getElementById('result-list').innerHTML = pageItems.map((p, i) => {
    const isW = watchedTitles.has(p.title);
    const initial = p.display_name.trim().charAt(0).toUpperCase();
    const year = new Date().getFullYear();
    const agePart = p.birth_year ? ' · age ' + (year - p.birth_year) : '';
    const descPart = p.description ? p.description.replace(/\\(.*?\\)/g, '').trim() : '';
    const safeName = p.display_name.replace(/"/g, '&quot;');
    const safeTitle = p.title.replace(/"/g, '&quot;');

    return `<div class="result-row" style="animation-delay:${i * 0.05}s">
      <div class="r-avatar" id="av-${CSS.escape(p.title)}">
        ${initial}
      </div>
      <div class="r-info">
        <div class="r-name">${p.display_name}</div>
        <div class="r-meta">${descPart}${agePart}</div>
      </div>
      <button
        class="add-btn ${isW ? 'added' : ''}"
        data-title="${safeTitle}"
        data-name="${safeName}"
        onclick="toggleWatch(this)"
        title="${isW ? 'Remove from watchlist' : 'Add to watchlist'}"
      >${isW ? '&#10003;' : '+'}</button>
    </div>`;
  }).join('');

  renderPagination(page, totalPages, q_);
  loadThumbnails(pageItems.map(r => r.title));
}

function renderPagination(page, total, q) {
  if (total <= 1) { document.getElementById('pagination').innerHTML = ''; return; }
  const container = document.getElementById('pagination');
  let html = '';
  const pages = [];

  // Always show first, last, current ± 1
  const show = new Set([1, total, page - 1, page, page + 1].filter(p => p >= 1 && p <= total));
  const sorted = [...show].sort((a, b) => a - b);

  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) {
      html += '<span class="page-dots">···</span>';
    }
    html += `<button class="page-btn ${p === page ? 'active' : ''}"
      onclick="renderPage(${p}, '${q}')">${p}</button>`;
  });

  container.innerHTML = html;
}

async function loadThumbnails(titles) {
  if (!titles.length) return;
  try {
    const url = 'https://en.wikipedia.org/w/api.php?action=query&prop=pageimages' +
      '&titles=' + encodeURIComponent(titles.join('|').replace(/_/g, ' ')) +
      '&pithumbsize=80&format=json&origin=*';
    const data = await (await fetch(url)).json();
    for (const p of Object.values(data.query?.pages || {})) {
      if (p.thumbnail?.source) {
        const key = p.title.replace(/ /g, '_');
        const el = document.getElementById('av-' + CSS.escape(key));
        if (el) el.innerHTML = `<img src="${p.thumbnail.source}" alt="" loading="lazy">`;
      }
    }
  } catch(e) {}
}

async function toggleWatch(btn) {
  const title = btn.getAttribute('data-title');
  const name  = btn.getAttribute('data-name');
  btn.classList.add('loading');

  if (watchedTitles.has(title)) {
    // Remove
    await fetch('/watch/' + encodeURIComponent(title), { method: 'DELETE' });
    watchedTitles.delete(title);
    btn.classList.remove('added', 'loading');
    btn.innerHTML = '+';
    btn.title = 'Add to watchlist';
  } else {
    // Add
    const r = await fetch('/watch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wiki_title: title, display_name: name })
    });
    btn.classList.remove('loading');
    if (r.ok) {
      watchedTitles.add(title);
      btn.classList.add('added');
      btn.innerHTML = '&#10003;';
      btn.title = 'Remove from watchlist';
    }
  }
}

init();
</script>
</body>
</html>
"""
