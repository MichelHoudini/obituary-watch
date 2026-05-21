"""
milestones.py — Watch count milestone notifier.
Runs 3x/week via GitHub Actions.
Checks if any wiki_title has crossed a new watcher milestone
and emails all watchers of that person.
"""

import os
import logging
import requests
from app.db import get_conn, _exec, _fetchall, USE_POSTGRES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL     = "Mortivox <noreply@mortivox.com>"
MILESTONES     = [10, 50, 100, 500, 1000, 2000, 3000]


def init_milestones_table():
    with get_conn() as conn:
        _exec(conn, """
            CREATE TABLE IF NOT EXISTS watch_milestones (
                wiki_title TEXT NOT NULL,
                milestone  INTEGER NOT NULL,
                notified_at TEXT NOT NULL,
                PRIMARY KEY (wiki_title, milestone)
            )
        """)
    log.info("watch_milestones table ready")


def get_watch_counts() -> list[dict]:
    """Returns list of {wiki_title, count} ordered by count desc."""
    with get_conn() as conn:
        cur = _exec(conn, """
            SELECT wiki_title, COUNT(*) as count
            FROM watches
            GROUP BY wiki_title
            ORDER BY count DESC
        """)
        return _fetchall(cur)


def get_notified_milestones(wiki_title: str) -> set[int]:
    with get_conn() as conn:
        ph = "%s" if USE_POSTGRES else "?"
        cur = _exec(conn,
            f"SELECT milestone FROM watch_milestones WHERE wiki_title={ph}",
            (wiki_title,)
        )
        rows = _fetchall(cur)
    return {r["milestone"] for r in rows}


def record_milestone(wiki_title: str, milestone: int):
    from app.db import utcnow
    with get_conn() as conn:
        if USE_POSTGRES:
            _exec(conn,
                "INSERT INTO watch_milestones (wiki_title, milestone, notified_at) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                (wiki_title, milestone, utcnow())
            )
        else:
            _exec(conn,
                "INSERT OR IGNORE INTO watch_milestones (wiki_title, milestone, notified_at) VALUES (?,?,?)",
                (wiki_title, milestone, utcnow())
            )


def get_emails_for(wiki_title: str) -> list[str]:
    with get_conn() as conn:
        ph = "%s" if USE_POSTGRES else "?"
        cur = _exec(conn,
            f"SELECT email FROM watches WHERE wiki_title={ph}",
            (wiki_title,)
        )
        rows = _fetchall(cur)
    return [r["email"] for r in rows]


def send_milestone_email(email: str, display_name: str, wiki_title: str, count: int, milestone: int):
    wiki_url = f"https://en.wikipedia.org/wiki/{wiki_title}"
    html = f"""
    <div style="background:#080808;color:#e8e4dc;font-family:'Courier New',monospace;padding:40px;max-width:600px;margin:0 auto">
      <div style="text-align:center;margin-bottom:32px">
        <div style="font-size:48px;letter-spacing:0.1em;color:#c8b89a;font-weight:bold">{milestone}</div>
        <div style="font-size:11px;letter-spacing:0.3em;text-transform:uppercase;color:#5a5650;margin-top:4px">watchers</div>
      </div>
      <h2 style="color:#c8b89a;letter-spacing:0.15em;text-transform:uppercase;margin-bottom:16px">{display_name}</h2>
      <p style="font-size:15px;line-height:1.8;color:#e8e4dc">
        You and <strong style="color:#c8b89a">{count - 1} other people</strong> are watching when
        <strong style="color:#c8b89a">{display_name}</strong> dies.
      </p>
      <div style="margin:32px 0;border-top:1px solid #1a1814"></div>
      <a href="{wiki_url}"
         style="font-size:11px;color:#c8b89a;letter-spacing:0.1em;text-transform:uppercase;text-decoration:none;border-bottom:1px solid #3a3428;padding-bottom:2px">
        View on Wikipedia →
      </a>
      <p style="margin-top:48px;font-size:11px;color:#3a3630;letter-spacing:0.1em">
        mortivox.com — know before everyone else
      </p>
    </div>
    """
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={
            "from": FROM_EMAIL,
            "to": [email],
            "subject": f"{milestone} people are watching when {display_name} dies",
            "html": html,
        }
    )
    if resp.status_code != 200:
        log.error(f"Failed to send to {email}: {resp.text}")


def run():
    log.info("Running milestone checker...")
    init_milestones_table()

    counts = get_watch_counts()
    log.info(f"Found {len(counts)} watched titles")

    for row in counts:
        wiki_title   = row["wiki_title"]
        count        = row["count"]
        display_name = wiki_title.replace("_", " ")

        notified = get_notified_milestones(wiki_title)
        new_milestones = [m for m in MILESTONES if m <= count and m not in notified]

        if not new_milestones:
            continue

        emails = get_emails_for(wiki_title)
        log.info(f"{display_name}: {count} watchers, new milestones: {new_milestones}")

        for milestone in new_milestones:
            for email in emails:
                send_milestone_email(email, display_name, wiki_title, count, milestone)
                log.info(f"  Sent milestone {milestone} to {email}")
            record_milestone(wiki_title, milestone)

    log.info("Milestone check complete.")


if __name__ == "__main__":
    run()
