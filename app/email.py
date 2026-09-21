"""
email.py — Send death notification emails via Resend.
Uses noreply@mortivox.com (domínio verificado no Resend).
Sender: Mortivox <noreply@mortivox.com>
"""

import html as _html
import logging
import os

import httpx

from app.dates import format_death_date_for_email

log = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL     = "Mortivox <noreply@mortivox.com>"
RESEND_URL     = "https://api.resend.com/emails"


APP_BASE_URL = os.environ.get("APP_BASE_URL", "https://mortivox.com")


def send_death_notification(
    to_email:     str,
    person_name:  str,
    wiki_title:   str,
    death_date:   str,
    wiki_url:     str,
    edit_url:     str | None = None,
    cancel_token: str | None = None,
) -> bool:
    """Send a death notification email. Returns True if sent successfully."""

    if not RESEND_API_KEY:
        log.warning("RESEND_API_KEY not set — skipping email")
        return False

    safe_name   = _html.escape(person_name)
    safe_date   = format_death_date_for_email(death_date)
    safe_date_h = _html.escape(safe_date)
    edit_link   = (
        f'\n<p style="margin:0 0 12px"><a href="{_html.escape(edit_url)}" '
        f'style="color:#c8b89a">See the Wikipedia edit that detected this →</a></p>'
        if edit_url else ""
    )

    cancel_url = (
        f"{APP_BASE_URL}/cancel?token={cancel_token}"
        if cancel_token
        else f"{APP_BASE_URL}/unsubscribe"
    )
    safe_cancel = _html.escape(cancel_url)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="background:#080808;margin:0;padding:0;font-family:'Courier New',monospace">
  <div style="max-width:520px;margin:0 auto;padding:48px 32px">

    <div style="text-align:center;margin-bottom:40px">
      <div style="font-size:11px;letter-spacing:0.3em;text-transform:uppercase;color:#5a5650;margin-bottom:8px">ObituaryWatch</div>
      <div style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#3a3630">know before everyone else</div>
    </div>

    <div style="border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:28px;background:#000;margin-bottom:24px">
      <div style="font-size:10px;letter-spacing:0.3em;text-transform:uppercase;color:#5a5650;margin-bottom:16px">Death detected</div>
      <div style="font-size:1.5rem;color:#f0ece4;letter-spacing:0.08em;margin-bottom:8px;font-weight:400">{safe_name}</div>
      <div style="font-size:12px;color:#5a5650;margin-bottom:20px">{safe_date_h}</div>
      <div style="border-top:1px solid #111;padding-top:16px">
        <p style="margin:0 0 12px;font-size:13px;color:#8a8278;line-height:1.6">
          Wikipedia has registered the death of <strong style="color:#c8c0b8">{safe_name}</strong>.
          You are receiving this email because you are watching this person on ObituaryWatch.
        </p>
        {edit_link}
        <a href="{_html.escape(wiki_url)}"
           style="display:inline-block;border:1px solid #4a4038;color:#c8b89a;text-decoration:none;
                  padding:10px 20px;border-radius:50px;font-size:12px;letter-spacing:0.1em;
                  text-transform:uppercase;margin-top:4px">
          View Wikipedia article →
        </a>
      </div>
    </div>

    <div style="text-align:center;font-size:11px;color:#3a3630;line-height:1.8">
      You watched <strong style="color:#5a5650">{safe_name}</strong> on ObituaryWatch.<br>
      This is an automated notification. Do not reply to this email.<br>
      <a href="{safe_cancel}" style="color:#3a3630">Unsubscribe</a>
    </div>

  </div>
</body>
</html>"""

    plain = (
        f"ObituaryWatch — Death detected\n\n"
        f"{person_name} has died.\n"
        f"Date: {safe_date}\n\n"
        f"Wikipedia: {wiki_url}\n"
        + (f"Edit: {edit_url}\n" if edit_url else "")
        + f"\nTo unsubscribe: {cancel_url}\n"
    )

    list_unsub_value = f"<{cancel_url}>"
    if cancel_token:
        list_unsub_value = f"<mailto:noreply@mortivox.com?subject=unsubscribe>, <{cancel_url}>"

    try:
        r = httpx.post(
            RESEND_URL,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "from":    FROM_EMAIL,
                "to":      [to_email],
                "subject": f"ObituaryWatch: {person_name} has died",
                "html":    html,
                "text":    plain,
                "headers": {
                    "List-Unsubscribe":      list_unsub_value,
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                },
            },
            timeout=10,
        )
        if r.status_code in (200, 201):
            log.info(f"Email sent to {to_email} for {person_name}")
            return True
        else:
            log.error(f"Resend error {r.status_code}: {r.text}")
            return False
    except Exception as e:
        log.error(f"Email send failed: {e}")
        return False


def send_watch_confirmation(
    to_email:    str,
    person_name: str,
    wiki_url:    str,
) -> bool:
    """Send a confirmation email when someone starts watching a person."""

    if not RESEND_API_KEY:
        return False

    safe_name  = _html.escape(person_name)
    safe_email = _html.escape(to_email)

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="background:#080808;margin:0;padding:0;font-family:'Courier New',monospace">
  <div style="max-width:520px;margin:0 auto;padding:48px 32px">

    <div style="text-align:center;margin-bottom:40px">
      <div style="font-size:11px;letter-spacing:0.3em;text-transform:uppercase;color:#5a5650;margin-bottom:8px">ObituaryWatch</div>
    </div>

    <div style="border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:28px;background:#000">
      <div style="font-size:10px;letter-spacing:0.3em;text-transform:uppercase;color:#5a5650;margin-bottom:16px">Watching confirmed</div>
      <div style="font-size:1.3rem;color:#f0ece4;letter-spacing:0.08em;margin-bottom:16px">{safe_name}</div>
      <p style="font-size:13px;color:#8a8278;line-height:1.6;margin:0 0 20px">
        You will receive an email at <strong style="color:#c8c0b8">{safe_email}</strong>
        when Wikipedia registers the death of <strong style="color:#c8c0b8">{safe_name}</strong>.
      </p>
      <a href="{_html.escape(wiki_url)}"
         style="display:inline-block;border:1px solid #4a4038;color:#c8b89a;text-decoration:none;
                padding:10px 20px;border-radius:50px;font-size:12px;letter-spacing:0.1em;text-transform:uppercase">
        View Wikipedia article →
      </a>
    </div>

    <div style="text-align:center;font-size:11px;color:#3a3630;margin-top:24px;line-height:1.8">
      ObituaryWatch monitors Wikipedia for you.<br>
      This is an automated message. Do not reply.
    </div>

  </div>
</body>
</html>"""

    try:
        r = httpx.post(
            RESEND_URL,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "from":    FROM_EMAIL,
                "to":      [to_email],
                "subject": f"ObituaryWatch: You're now watching {person_name}",
                "html":    html,
            },
            timeout=10,
        )
        log.info(f"Confirmation email to {to_email}: status={r.status_code} body={r.text[:200]}")
        return r.status_code in (200, 201)
    except Exception as e:
        log.error(f"Confirmation email failed: {e}")
        return False
