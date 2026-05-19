const watched = new Set();
let searchTimer = null;
let focusIndex = -1;
let lastResults = [];
let lastQuery = '';
const YEAR = new Date().getFullYear();

function hl(text, q) {
  if (!q) return text;
  const safe = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return text.replace(new RegExp('(' + safe + ')', 'gi'),
    '<span class="result-highlight">$1</span>');
}

function renderResults(results, query, thumbs) {
  const box = document.getElementById('search-results');
  if (!results.length) {
    box.innerHTML = '<div class="search-empty">no results found.</div>';
    return;
  }
  thumbs = thumbs || {};
  box.innerHTML = results.map((p, i) => {
    const isW = watched.has(p.title);
    const safeTitle = p.title.replace(/"/g, '&quot;');
    const safeName = p.display_name.replace(/"/g, '&quot;');
    const thumb = thumbs[p.title] || thumbs[p.title.replace(/_/g, ' ')];
    const initial = p.display_name.trim().charAt(0).toUpperCase();
    const avatar = thumb
      ? `<div class="result-avatar"><img src="${thumb}" alt="" loading="lazy"></div>`
      : `<div class="result-avatar">${initial}</div>`;
    const meta = p.description ? `<div class="result-meta">${p.description}</div>` : '';
    const age = p.birth_year ? `<div class="result-age">age ${YEAR - p.birth_year}</div>` : '';
    return `<div class="search-result${i === focusIndex ? ' focused' : ''}"
      data-title="${safeTitle}" data-name="${safeName}" onclick="addPerson(this)">
      ${avatar}
      <div class="result-body">
        <div class="result-name">${hl(p.display_name, query)}</div>
        ${meta}${age}
      </div>
      <div class="result-add${isW ? ' watching' : ''}">${isW ? '&#10003;' : '+'}</div>
    </div>`;
  }).join('');
}

async function fetchThumbnails(titles) {
  try {
    const url = 'https://en.wikipedia.org/w/api.php?action=query&prop=pageimages' +
      '&titles=' + encodeURIComponent(titles.join('|').replace(/_/g, ' ')) +
      '&pithumbsize=60&format=json&origin=*';
    const data = await (await fetch(url)).json();
    const out = {};
    for (const p of Object.values(data.query?.pages || {})) {
      if (p.thumbnail?.source) out[p.title.replace(/ /g, '_')] = p.thumbnail.source;
    }
    return out;
  } catch(e) { return {}; }
}

function handleSearch(val) {
  clearTimeout(searchTimer);
  const spinner = document.getElementById('search-spinner');
  focusIndex = -1;
  if (!val.trim()) {
    spinner.classList.remove('active');
    return;
  }
  if (val.length >= 2) spinner.classList.add('active');
  searchTimer = setTimeout(() => goToResults(val.trim()), 500);
}

function goToResults(q) {
  document.getElementById('search-spinner').classList.remove('active');
  window.location.href = '/results?q=' + encodeURIComponent(q);
}

async function doSearch(q) {
  const box = document.getElementById('search-results');
  const spinner = document.getElementById('search-spinner');
  lastQuery = q;
  if (q.length < 2) { box.style.display = 'none'; spinner.classList.remove('active'); return; }
  try {
    // Step 1: Wikipedia opensearch — ranked by popularity, best for famous names
    const wpUrl = 'https://en.wikipedia.org/w/api.php?action=opensearch' +
      '&search=' + encodeURIComponent(q) + '&limit=8&namespace=0&format=json&origin=*';
    const [, titles, descs, urls] = await (await fetch(wpUrl)).json();

    spinner.classList.remove('active');
    if (document.getElementById('search-input').value.trim() !== q) return;

    // Step 2: Enrich with Wikidata descriptions (async, non-blocking)
    const baseResults = titles.map((t, i) => ({
      title: t.replace(/ /g, '_'),
      display_name: t,
      description: descs[i] || '',
      birth_year: extractBirthYear(descs[i] || ''),
      url: urls[i]
    }));

    // Filter out non-persons and obviously dead people (year ranges in description)
    const rejectKw = [
      'film','album','song','discography','filmography','soundtrack',
      'television series','tv series','video game','software',
      'municipality','commune','district','river','lake','mountain','building',
      'male given name','female given name','given name','family name','surname'
    ];
    lastResults = baseResults.filter(r => {
      const d = r.description.toLowerCase();
      if (rejectKw.some(kw => d.includes(kw))) return false;
      // Filter out people with death year ranges like (1865-1918) or (1947–2022)
      if (/\(\d{4}[\u2013\-]\d{4}\)/.test(r.description)) return false;
      // Filter out descriptions ending in a death year like "journalist (1947-2022)"
      if (/\d{4}[\u2013\-]\d{4}/.test(r.description)) return false;
      return true;
    }).slice(0, 6);

    renderResults(lastResults, q);

    // Async: fetch thumbnails
    if (lastResults.length) {
      fetchThumbnails(lastResults.map(r => r.title)).then(thumbs => {
        if (document.getElementById('search-input').value.trim() === q)
          renderResults(lastResults, q, thumbs);
      });
    }

    // Async: enrich descriptions from Wikidata
    enrichFromWikidata(lastResults, q);

  } catch(e) {
    spinner.classList.remove('active');
    box.innerHTML = '<div class="search-empty">error searching. try again.</div>';
  }
}

function extractBirthYear(text) {
  const m = text.match(/born\s+(\d{4})|\(born\s+(\d{4})/);
  return m ? parseInt(m[1]||m[2]) : null;
}

async function enrichFromWikidata(results, query) {
  // Fetch richer descriptions AND check if person is dead
  try {
    const toRemove = new Set();
    for (const r of results) {
      const url = 'https://www.wikidata.org/w/api.php?action=wbsearchentities' +
        '&search=' + encodeURIComponent(r.display_name) +
        '&language=en&type=item&limit=3&format=json&origin=*';
      const data = await (await fetch(url)).json();
      const match = (data.search||[]).find(item =>
        item.label.toLowerCase() === r.display_name.toLowerCase()
      );
      if (match) {
        // Check if person has death date via Wikidata entity
        const entityUrl = 'https://www.wikidata.org/w/api.php?action=wbgetentities' +
          '&ids=' + match.id + '&props=claims&format=json&origin=*';
        const entityData = await (await fetch(entityUrl)).json();
        const claims = entityData.entities?.[match.id]?.claims || {};
        // P570 = date of death
        if (claims.P570) {
          toRemove.add(r.title);
          continue;
        }
        // Enrich description if empty
        if (match.description && !r.description) {
          r.description = match.description;
          r.birth_year = extractBirthYear(match.description);
        }
      }
    }
    // Remove dead people and re-render
    if (toRemove.size > 0) {
      lastResults = lastResults.filter(r => !toRemove.has(r.title));
      if (document.getElementById('search-input').value.trim() === query) {
        fetchThumbnails(lastResults.map(x => x.title)).then(thumbs => {
          if (document.getElementById('search-input').value.trim() === query)
            renderResults(lastResults, query, thumbs);
        });
      }
    }
  } catch(e) {}
}

function handleKey(e) {
  if (e.key === 'Enter') {
    const val = document.getElementById('search-input').value.trim();
    if (val.length >= 2) goToResults(val);
  }
  if (e.key === 'Escape') {
    document.getElementById('search-input').value = '';
  }
}

document.addEventListener('click', e => {
  if (!document.getElementById('search-wrap').contains(e.target)) {
    document.getElementById('search-results').style.display = 'none';
    focusIndex = -1;
  }
});

async function addPerson(el) {
  const title = el.getAttribute('data-title');
  const name = el.getAttribute('data-name');
  if (watched.has(title)) return;
  const btn = el.querySelector('.result-add');
  if (btn) btn.textContent = '...';
  const r = await fetch('/watch', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({wiki_title: title, display_name: name})
  });
  const d = await r.json();
  if (r.ok) {
    watched.add(title);
    if (btn) { btn.textContent = '\u2713'; btn.classList.add('watching'); }
    if (d.added) addPreviewPill(name, title);
    setTimeout(() => {
      document.getElementById('search-results').style.display = 'none';
      document.getElementById('search-input').value = '';
      focusIndex = -1;
    }, 700);
  }
}

function toggleCats() {
  const btn = document.getElementById('cat-toggle');
  const sec = document.getElementById('cat-section');
  const isOpen = sec.style.display === 'block';
  sec.style.display = isOpen ? 'none' : 'block';
  btn.classList.toggle('open', !isOpen);
}

async function selectCategory(btn) {
  const cat = btn.getAttribute('data-cat');
  document.querySelectorAll('.cat-card').forEach(c => c.classList.remove('selected'));
  btn.classList.add('selected');
  const msg = document.getElementById('cat-msg');
  msg.textContent = 'adding all living ' + cat + ' from Wikidata... (~15s)';
  try {
    const r = await fetch('/watch/category', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({category: cat, limit: 200})
    });
    const d = await r.json();
    if (r.ok) {
      msg.textContent = 'added ' + d.newly_added + ' people to your watchlist.';
      loadWatchlist();
    } else {
      msg.textContent = 'error adding category. try again.';
      btn.classList.remove('selected');
    }
  } catch(e) {
    msg.textContent = 'network error. try again.';
    btn.classList.remove('selected');
  }
}

async function loadWatchlist() {
  try {
    const data = await (await fetch('/watched')).json();
    if (!data.length) return;
    data.forEach(p => watched.add(p.wiki_title));
    document.getElementById('watchlist-preview').innerHTML =
      data.slice(0, 12).map((p, i) => makePill(p.display_name, p.wiki_title, i)).join('');
    document.getElementById('watchlist-section').style.display = 'block';
  } catch(e) {}
}

function makePill(name, title, index) {
  const t = title.replace(/"/g, '&quot;');
  const delay = (index || 0) * 0.05;
  return `<div class="preview-pill" style="animation-delay:${delay}s">
    <span class="preview-pill-name">${name}</span>
    <button class="preview-pill-x" data-title="${t}" onclick="removeWatch(this)">&times;</button>
  </div>`;
}

function addPreviewPill(name, title) {
  document.getElementById('watchlist-section').style.display = 'block';
  document.getElementById('watchlist-preview').insertAdjacentHTML('afterbegin', makePill(name, title));
}

async function removeWatch(btn) {
  const title = btn.getAttribute('data-title');
  await fetch('/watch/' + encodeURIComponent(title), {method: 'DELETE'});
  watched.delete(title);
  btn.closest('.preview-pill').remove();
}

async function subscribe() {
  const email = document.getElementById('email-input').value.trim();
  const msg = document.getElementById('email-msg');
  if (!email || !email.includes('@')) { msg.textContent = 'enter a valid email.'; return; }
  const r = await fetch('/subscribe', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({email})
  });
  if (r.ok) {
    msg.textContent = 'subscribed. you will be notified when someone dies.';
    document.getElementById('email-input').value = '';
  }
}

document.getElementById('email-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') subscribe();
});

loadWatchlist();
