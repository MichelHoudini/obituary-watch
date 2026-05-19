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
  const box = document.getElementById('search-results');
  const spinner = document.getElementById('search-spinner');
  focusIndex = -1;
  if (!val.trim()) {
    box.style.display = 'none';
    spinner.classList.remove('active');
    return;
  }
  box.style.display = 'block';
  if (val.length >= 2) spinner.classList.add('active');
  searchTimer = setTimeout(() => doSearch(val.trim()), 320);
}

async function doSearch(q) {
  const box = document.getElementById('search-results');
  const spinner = document.getElementById('search-spinner');
  lastQuery = q;
  if (q.length < 2) { box.style.display = 'none'; spinner.classList.remove('active'); return; }
  try {
    // Search Wikidata directly from browser (no 403 issues)
    const wdUrl = 'https://www.wikidata.org/w/api.php?action=wbsearchentities' +
      '&search=' + encodeURIComponent(q) +
      '&language=en&uselang=en&type=item&limit=12&format=json&origin=*';
    const wdResp = await fetch(wdUrl);
    const wdData = await wdResp.json();

    spinner.classList.remove('active');
    if (document.getElementById('search-input').value.trim() !== q) return;

    // Filter to people and build results
    const rejectKw = [
      'film','album','song','series','novel','city','village','company','software','game',
      'given name','family name','surname','commune','municipality','district','province',
      'river','lake','mountain','discography','concert','festival','tour','band','group',
      'documentary','television','broadcast','recording','compilation','soundtrack',
      'lollapalooza','montreux','performed','leurres','artwork','painting','building',
      'bishop','pope','cardinal','archbishop','saint','catholic','roman catholic',
      'physicist','chemist','mathematician','philosopher','theologian'
    ];
    const items = (wdData.search || []).filter(item => {
      const d = (item.description || '').toLowerCase();
      const label = (item.label || '').toLowerCase();
      if (!item.description || item.description.trim() === '') return false;
      if (rejectKw.some(kw => d.includes(kw) || label.includes(kw))) return false;
      if (/\d{4}/.test(item.label) && d === '') return false;
      // Filter out people who died before 1900
      const deathMatch = d.match(/(\d{4})[\u2013\-](\d{4})/);
      if (deathMatch) {
        const deathYear = parseInt(deathMatch[2]);
        if (deathYear && deathYear < 1900) return false;
      }
      return true;
    });
    // Sort: people with clear person keywords first
    const personKw = ['actor','actress','musician','singer','songwriter','rapper','athlete','footballer','director','writer','author','artist','presenter','born','politician','president','prime minister'];
    items.sort((a, b) => {
      const aIsPerson = personKw.some(k => (a.description||'').toLowerCase().includes(k)) ? 0 : 1;
      const bIsPerson = personKw.some(k => (b.description||'').toLowerCase().includes(k)) ? 0 : 1;
      if (aIsPerson !== bIsPerson) return aIsPerson - bIsPerson;
      return (b.description||'').length - (a.description||'').length;
    });
    // Fix birth year — only extract 4-digit years that look like birth years (1900-2010)
    // not years from descriptions like "president from 2007 to 2012"

    if (!items.length) {
      // Fallback to Wikipedia opensearch
      const wpUrl = 'https://en.wikipedia.org/w/api.php?action=opensearch' +
        '&search=' + encodeURIComponent(q) + '&limit=6&namespace=0&format=json&origin=*';
      const wpResp = await fetch(wpUrl);
      const [, titles, descs, urls] = await wpResp.json();
      lastResults = titles.map((t, i) => ({
        title: t.replace(/ /g,'_'), display_name: t,
        description: descs[i] || '', birth_year: null, url: urls[i]
      }));
    } else {
      lastResults = items.slice(0,6).map(item => {
        let desc = (item.description || '');
        if (desc.length > 80) desc = desc.slice(0,77) + '...';
        if (desc) desc = desc[0].toUpperCase() + desc.slice(1);
        const byMatch = desc.match(/born\s+(\d{4})|\(born\s+(\d{4})/);
        const birthYear = byMatch ? parseInt(byMatch[1]||byMatch[2]) : null;
        // Use label as title placeholder — will resolve on add
        return {
          title: item.label.replace(/ /g,'_'),
          display_name: item.label,
          description: desc,
          birth_year: birthYear,
          url: 'https://en.wikipedia.org/wiki/' + encodeURIComponent(item.label.replace(/ /g,'_')),
          wikidata_id: item.id
        };
      });
    }

    renderResults(lastResults, q);

    // Async: fetch thumbnails
    if (lastResults.length) {
      fetchThumbnails(lastResults.map(r => r.title)).then(thumbs => {
        if (document.getElementById('search-input').value.trim() === q)
          renderResults(lastResults, q, thumbs);
      });
    }
  } catch(e) {
    spinner.classList.remove('active');
    box.innerHTML = '<div class="search-empty">error searching. try again.</div>';
  }
}

function handleKey(e) {
  const box = document.getElementById('search-results');
  if (box.style.display === 'none') return;
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    focusIndex = Math.min(focusIndex + 1, lastResults.length - 1);
    renderResults(lastResults, lastQuery);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    focusIndex = Math.max(focusIndex - 1, -1);
    renderResults(lastResults, lastQuery);
  } else if (e.key === 'Enter' && focusIndex >= 0) {
    e.preventDefault();
    const el = box.querySelector('.search-result.focused');
    if (el) addPerson(el);
  } else if (e.key === 'Escape') {
    box.style.display = 'none';
    focusIndex = -1;
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
