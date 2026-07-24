# Analytics — Mortivox

Mortivox supports one optional env var for analytics:

```
ANALYTICS_HEAD_SNIPPET
```

Paste the **exact** tracking snippet your analytics provider (Plausible,
Umami, or anything else) gives you in its site settings — the whole thing,
script tags included — and set it as the value of this env var in Render.
It gets injected verbatim into every page's `<head>`.

If the env var is unset or empty, nothing is rendered and the site behaves
exactly as if analytics didn't exist. No script, no request, no dependency.

## Why a raw snippet instead of separate `ANALYTICS_PROVIDER`/`ANALYTICS_DOMAIN` vars

Analytics providers change their embed markup over time — for example,
Plausible's [October 2025 script
update](https://plausible.io/docs/script-update-guide) replaced the old
`<script defer data-domain="...">` tag with a unique two-tag snippet per
site, with no `data-domain` attribute at all. Trying to keep provider-shaped
env vars in sync with each provider's current format means the app code has
to change every time a provider changes their script — which is exactly
what happened once already in this repo (Phase 2A shipped a
Plausible/Umami-specific implementation that didn't match the snippet
Plausible actually gives new sites).

A single "paste the exact snippet" env var sidesteps this permanently: the
app never parses or reconstructs the tag, so it can't drift out of sync with
whatever the provider currently generates.

## Setting it up (Plausible)

1. Create a Plausible account: https://plausible.io/register
2. Add `mortivox.com` as a site in the Plausible dashboard
3. Go to the site's **Site Installation** settings and copy the snippet shown
   there verbatim
4. In Render, set `ANALYTICS_HEAD_SNIPPET` to that exact value
5. Redeploy (or wait for the next deploy) — no code change needed

## Custom events already wired up

The app fires these events via a safe `window.trackEvent(name, props)`
helper (always present, no-ops if no analytics script is loaded):

- `view_person_page`
- `click_monitor`
- `submit_watch`
- `watch_success`
- `watch_error`

Only non-personal fields are ever sent: `wiki_title`, `slug`, `page_type`,
`category`, `success`. Never email, never other personal data.

`trackEvent` calls `window.plausible(name, {props})` if `window.plausible`
exists as a function (true for both the old and the October 2025 Plausible
script format), or `window.umami.track(name, props)` if `window.umami.track`
exists. If neither is present — e.g. `ANALYTICS_HEAD_SNIPPET` is unset — it
silently does nothing.
