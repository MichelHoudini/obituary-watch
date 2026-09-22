# Watcher — architecture and risks

_Verified against `app/watcher.py`, `app/filters.py`, `.github/workflows/watcher.yml`, commit on branch `fix/perf-ci-backfill`._

---

## Where the watcher SSE stream runs

The watcher **does not run on Render**. It runs as a GitHub Actions job (`watcher.yml`) scheduled every 2 hours (`cron: '0 */2 * * *'`). Each run opens an SSE connection to `https://stream.wikimedia.org/v2/stream/recentchange`, processes events for up to 50 minutes, then the job exits and the connection closes.

The SSE loop is in `app/watcher.py:run()` → `sseclient.SSEClient(r).events()`. No SSE infrastructure lives on Render at all.

## What happens when Render hibernates

Render hibernation is **irrelevant to the watcher** because the watcher runs on GitHub Actions, not Render. If Render hibernates the web app, the watcher job continues unaffected.

What hibernation DOES affect:
- The watcher writes heartbeats to the Render Postgres DB every 60 seconds (`record_watcher_heartbeat()`). While Render wakes up connections on the first query, a cold wake after hibernation adds ~3–5 s of latency to the first DB write of a run. This has no impact on correctness.
- `/status` reads the heartbeat age to set `watcher_is_stale`. Stale threshold is 2.5 hours (`WATCHER_STALE_HOURS`). Since the job runs every 2 hours and runs for ~50 minutes, there is always a recent heartbeat in the DB during normal operation.

## Where `enrich_death` runs and whether Wikidata is reachable

`enrich_death(title)` is called in `app/watcher.py:158` immediately after `record_death()` returns `True`. It runs **inside the GitHub Actions job**, not on Render.

GitHub Actions runners have unrestricted outbound internet access, so Wikidata API calls succeed from there. Render's free tier also has outbound internet, but `enrich_death` is never called from Render code — the web app imports `app/filters.py` only for `match_watch()` and `should_notify_filter_watch()`, both of which are pure Python with no network calls.

The enrichment flow:
1. `enrich_death(title)` calls `_fetch_person_claims(title)` → Wikipedia API → gets QID.
2. For each occupation/location QID, calls `traverse_hierarchy()` → Wikidata API repeatedly.
3. Persists results via `update_death_enrichment()` to the Postgres DB.
4. Returns `{"occupation_qids": [...], "location_qids": [...]}`.

If any Wikidata call times out (10 s timeout), `_fetch_parents()` returns `[]` and enrichment continues with partial or empty arrays. Empty arrays mean no filter subscriptions will match — filter emails are simply not sent for that death.

## How `watcher_is_stale` is calculated

Defined in `app/main.py:_watcher_is_stale()`:

```
stale = (now − last_heartbeat) > WATCHER_STALE_HOURS  (default 2.5 h)
```

The heartbeat is written every `HEARTBEAT_INTERVAL = 60 s` during an active watcher run. Since the watcher job runs every 2 hours and each run lasts ~50 minutes, the maximum gap between runs is ~2 hours 10 minutes — well below the 2.5 h stale threshold. One missed job run would bring the gap to ~4 h 10 min, which crosses the threshold and causes `/status` to report `watcher_is_stale: true`.

If `watcher_health` is `null` (DB never had a heartbeat row), `_watcher_is_stale` returns `True`.

---

## Risks

| Risk | Severity | Status |
|---|---|---|
| Wikidata API unavailable during enrichment → empty QID arrays → filter subscribers never notified for that death | Medium | Known; no retry. Empty arrays are the silent outcome. |
| GitHub Actions job skipped (quota, billing, disabled repo) → no heartbeat → `watcher_is_stale=true` but no alert | Medium | `/status` exposes it; no automated alert configured. |
| Filter subscriptions were silently never notified (watcher called `get_emails_for` not `get_notifiable_emails_for_death`) | High | **Fixed in PR #18** (`fix/perf-ci-backfill`). |
| Ingestor path also never sent filter emails | High | **Fixed in PR #18** via `_notify_filter_subscribers()`. |
| Wikipedia SSE stream closes mid-run (happens frequently) | Low | `run()` catches the exception, sleeps with exponential backoff, reconnects. |
| Deaths detected between the 2-hour job windows are missed until the next run | Medium | By design. Mitigation: ingestor runs every 6 hours and backtracks 3 days. |
| Watcher job timeout (50 min limit) silently truncates the watch window | Low | The job uses `timeout 2900 python -m app.watcher || true`. Connection is cleanly dropped and restarted on the next scheduled run. |

---

_No code changes were made in this file. This is documentation only._
