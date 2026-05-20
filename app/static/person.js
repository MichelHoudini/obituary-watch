// person.js — loaded by /person page
// LANG and TITLE are set as global vars by the server

const YEAR = new Date().getFullYear();

const OCCS = [
  ['Actor',        ['actor','actress']],
  ['Musician',     ['musician','singer','songwriter','rapper','composer','guitarist']],
  ['Director',     ['director','filmmaker']],
  ['Writer',       ['writer','author','novelist','poet','screenwriter','journalist']],
  ['Politician',   ['politician','president','prime minister','senator','governor']],
  ['Athlete',      ['athlete','footballer','basketball player','tennis player','boxer']],
  ['Scientist',    ['scientist','physicist','biologist','astronomer','mathematician']],
  ['Artist',       ['artist','painter','sculptor','photographer']],
  ['Comedian',     ['comedian','comic']],
  ['Entrepreneur', ['entrepreneur','businessman','businesswoman','ceo']],
  ['Model',        ['model']],
];

function getOcc(desc) {
  if (!desc) return '';
  const d = desc.toLowerCase();
  for (const [l, ks] of OCCS) if (ks.some(k => d.includes(k))) return l;
  return desc.split(/[,.(]/)[0].trim().slice(0, 30);
}

function getBirthDate(text) {
  if (!text) return null;
  const m = text.match(/\(born\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4})/i);
  return m ? m[1] : null;
}

function getBirthYear(text) {
  if (!text) return null;
  const m = text.match(/born.*?(\d{4})/i);
  return m ? parseInt(m[1]) : null;
}

function isDead(wikitext) {
  if (!wikitext) return false;
  // Check for death_date field with a non-empty value
  const patterns = [
    /death_date\s*=\s*([^\|\}\n]{3,})/,
    /death date\s*=\s*([^\|\}\n]{3,})/,
    // Hungarian
    /hal[aá]loz[aá]si.d[aá]tum\s*=\s*([^\|\}\n]{3,})/i,
    // Common across many languages
    /\|\s*halott\s*=\s*([^\|\}\n]{3,})/i,
    /tod(?:esjahr|esdatum)\s*=\s*([^\|\}\n]{3,})/i,
    /date.?de.?d[eé]c[eè]s\s*=\s*([^\|\}\n]{3,})/i,
    /fecha.?de.?fallecimiento\s*=\s*([^\|\}\n]{3,})/i,
    /data.?(?:di.?)?morte\s*=\s*([^\|\}\n]{3,})/i,
    /data.?falecimento\s*=\s*([^\|\}\n]{3,})/i,
  ];
  for (const p of patterns) {
    const m = wikitext.match(p);
    if (m && m[1].trim().length > 0) return true;
  }
  return false;
}

// Show skeleton while loading
document.getElementById('main').innerHTML = `
  <div class="card">
    <div class="person-top">
      <div class="photo-placeholder skeleton" style="border:none"></div>
      <div style="flex:1;padding-top:6px">
        <div class="skeleton" style="height:20px;width:55%;margin-bottom:10px;border-radius:10px"></div>
        <div class="skeleton" style="height:13px;width:35%;border-radius:6px"></div>
      </div>
    </div>
    <div class="skeleton" style="height:13px;margin-bottom:8px;border-radius:6px"></div>
    <div class="skeleton" style="height:13px;width:70%;border-radius:6px"></div>
  </div>`;

async function load() {
  try {
    const apiBase = `https://${LANG}.wikipedia.org/w/api.php`;
    const url = apiBase + '?action=query' +
      '&titles=' + encodeURIComponent(TITLE.replace(/_/g, ' ')) +
      '&prop=extracts|pageimages|description|revisions' +
      '&exintro=true&explaintext=true&pithumbsize=200&redirects=true' +
      '&rvprop=content&rvslots=main' +
      '&format=json&origin=*';

    const data = await (await fetch(url)).json();
    const page = Object.values(data.query.pages)[0];

    if (page.missing !== undefined) {
      document.getElementById('main').innerHTML =
        '<div style="text-align:center;color:#5a5650;padding:60px 0;font-style:italic">Page not found on Wikipedia.</div>';
      return;
    }

    // Check if person is already dead
    const wikitext = page.revisions?.[0]?.slots?.main?.['*'] ||
                     page.revisions?.[0]?.slots?.main?.content || '';
    if (isDead(wikitext)) {
      document.getElementById('main').innerHTML =
        '<div style="text-align:center;color:#5a5650;padding:60px 0;font-style:italic">This person has already passed away.<br>ObituaryWatch only monitors living people.</div>';
      return;
    }

    const name    = page.title || TITLE.replace(/_/g, ' ');
    const desc    = page.description || '';
    const extract = (page.extract || '').slice(0, 320);
    const thumb   = page.thumbnail?.source || '';
    const job     = getOcc(desc);
    const bd      = getBirthDate(extract);
    const by      = getBirthYear(extract);
    const age     = by ? YEAR - by : null;

    document.title = name + ' — ObituaryWatch';

    const photo = thumb
      ? `<img src="${thumb}" alt="${name}" class="photo">`
      : `<div class="photo-placeholder">${name.charAt(0).toUpperCase()}</div>`;

    let rows = '';
    if (job) rows += `<div class="info-row"><span class="info-key">Occupation</span><span class="info-val">${job}</span></div>`;
    if (bd)  rows += `<div class="info-row"><span class="info-key">Born</span><span class="info-val">${bd}${age ? ' · age ' + age : ''}</span></div>`;
    else if (age) rows += `<div class="info-row"><span class="info-key">Age</span><span class="info-val">${age}</span></div>`;

    const first = name.split(' ')[0];
    const wikiUrl = `https://${LANG}.wikipedia.org/wiki/${TITLE}`;

    document.getElementById('main').innerHTML = `
      <div class="card">
        <div class="person-top">
          ${photo}
          <div>
            <div class="person-name">${name}</div>
            <div class="person-occ">${desc}</div>
          </div>
        </div>
        ${rows}
        ${extract ? '<div class="extract">' + extract + '...</div>' : ''}
        <a class="wiki-link" href="${wikiUrl}" target="_blank">view on Wikipedia &rarr;</a>
      </div>
      <div class="card">
        <div class="watch-label">Get notified when ${first} dies</div>
        <input class="input" id="email" type="email" placeholder="your@email.com"
          onkeydown="if(event.key==='Enter') doWatch()">
        <button class="btn watch-btn" onclick="doWatch()">Watch</button>
        <div class="err" id="err"></div>
        <div class="success" id="ok">&#10003; You're watching ${name}. We'll email you when Wikipedia registers their death.</div>
      </div>`;

  } catch(e) {
    console.error(e);
    document.getElementById('main').innerHTML =
      '<div style="text-align:center;color:#5a5650;padding:60px 0;font-style:italic">Error loading. Please try again.</div>';
  }
}

async function doWatch() {
  const email = document.getElementById('email').value.trim();
  const err   = document.getElementById('err');
  const btn   = document.querySelector('.watch-btn');
  if (!email || !email.includes('@')) { err.textContent = 'enter a valid email.'; return; }
  err.textContent = '';
  btn.textContent = 'sending...';
  btn.disabled = true;
  btn.style.opacity = '0.5';
  const r = await fetch('/watch', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({wiki_title: TITLE, email, lang: LANG})
  });
  if (r.ok) {
    document.getElementById('email').style.display = 'none';
    btn.style.display = 'none';
    document.getElementById('ok').style.display = 'block';
  } else {
    btn.textContent = 'Watch';
    btn.disabled = false;
    btn.style.opacity = '1';
    err.textContent = 'something went wrong. try again.';
  }
}

load();
