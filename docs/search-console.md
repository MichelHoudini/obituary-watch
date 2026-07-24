# Google Search Console — Mortivox

This is an operational checklist for getting mortivox.com indexed by Google
and for monitoring indexing health after Phase 1/2A ships. It does not
require any code changes; Search Console verification and sitemap submission
are done entirely through Google's dashboard and DNS/HTML, not the app.

## 1. Add the property

1. Go to https://search.google.com/search-console
2. Click **Add property**
3. Choose **Domain** (covers `mortivox.com`, `www.mortivox.com`, and both
   `http`/`https`) rather than **URL prefix**, since Domain verification is
   less brittle if the site later adds `www` or changes protocol.

## 2. Verify the domain

Domain-property verification is done via a DNS TXT record (Search Console
shows the exact value to add):

1. Search Console gives you a TXT record like:
   `google-site-verification=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
2. Add that TXT record at the DNS provider where `mortivox.com` is
   registered (Spaceship, per project notes).
3. Wait for DNS propagation (usually minutes, can take up to ~24h) and click
   **Verify** in Search Console.

Alternative if DNS access isn't convenient: use **URL prefix** verification
instead with the HTML file or meta-tag method. This only verifies
`https://mortivox.com`, not other variants, but avoids touching DNS. This
repo does not currently define a verification env var — if we ever need one,
it must be added as an env var (e.g. `GOOGLE_SITE_VERIFICATION`) rather than
hardcoded, since it's tied to a specific Search Console property.

## 3. Submit the sitemap

Once verified:

1. In Search Console, go to **Sitemaps** (left sidebar)
2. Enter `sitemap.xml` (relative to the verified property) or the full URL:
   `https://mortivox.com/sitemap.xml`
3. Click **Submit**

The sitemap is generated dynamically by `/sitemap.xml` and includes:
- `/`
- `/people`
- `/deaths`
- `/lists/most-monitored`
- `/lists/oldest-living`
- `/lists/actors`
- `/lists/musicians`
- one `/person/{slug}` entry per catalog person

No manual sitemap file exists — it always reflects the current catalog, so
there's nothing to regenerate or re-upload when the catalog changes.

## 4. What to check in the first 7 days

Search Console data lags by 1–3 days, so don't expect same-day results.
Check daily or every other day:

- **Coverage / Pages report**: watch the "Indexed" count climb toward the
  number of URLs in the sitemap. A flat or falling count after day 3–4 is
  worth investigating.
- **Sitemaps report**: confirm the sitemap shows "Success" status and the
  "Discovered URLs" count matches what `/sitemap.xml` actually returns.
- **URL Inspection tool**: manually inspect 2–3 `/person/{slug}` URLs and
  the homepage to confirm Google can fetch and render them (checks for
  robots blocking, redirect issues, or unrendered JS-only content).
- **Performance report**: initially empty; first impressions typically
  appear after Google's first real crawl+index pass, not immediately after
  submission.

## 5. Indexing errors to watch for

These are the errors most likely to show up for this specific app, and what
they'd mean here:

- **"Discovered – currently not indexed"**: normal for the first few days on
  a brand-new domain; only worth acting on if it persists past ~2 weeks for
  the homepage or high-priority list pages.
- **"Crawled – currently not indexed"**: Google fetched the page but chose
  not to index it — often a sign of thin/duplicate content. Since
  `/person/{slug}` pages are templated, keep an eye on whether Google treats
  them as too similar to each other; the per-person Q&A copy (added in
  Phase 2A) exists partly to reduce this risk.
- **"Not found (404)"**: check whether the URL came from a stale sitemap
  entry for a catalog person that was later removed, or a `/person/{slug}`
  slug that doesn't resolve — see `find_catalog_person`/`title_to_slug` in
  `app/catalog.py`.
- **"Server error (5xx)"**: check Render logs for the timestamp Search
  Console reports; cross-reference with `/status` (`watcher_is_stale` is
  unrelated to this, but a Render cold-start or DB connection issue would
  show up here).
- **"Redirect error"**: this app doesn't currently issue redirects for these
  routes, so this would indicate something at the Render/DNS layer (e.g. a
  misconfigured `www` → non-`www` redirect), not app code.
- **robots.txt blocking**: `/robots.txt` allows `/` for all user-agents by
  default (see `app/main.py`), so this shouldn't happen unless the file
  itself fails to load — worth a quick manual check at
  `https://mortivox.com/robots.txt` if pages aren't being crawled at all.

## Notes for Phase 2A+

- No Google verification code is added to the app in this phase. If/when
  we do add one, it should be read from an env var and default to omitted
  (matching the same fail-safe pattern used for `ANALYTICS_PROVIDER`), so
  the site never breaks or leaks a verification string if the var is unset.
- Sitemap correctness (which paths it includes) is enforced by test/curl
  checks in Phase 2A validation, not by this document — this document is
  about the Search Console side, not the app side.
