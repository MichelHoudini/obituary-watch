"""
Simula a morte do Nicolas Cage e envia email para brainiackson@gmail.com
"""
import os, psycopg2, requests

DATABASE_URL = "postgresql://postgres.nhlnmqcrecaufaetytbi:xn.3K9WwtUqtPy.@aws-1-sa-east-1.pooler.supabase.com:5432/postgres"
RESEND_API_KEY = "re_MRC9TYFG_EFXWhMD6Q3uSGM58Rf6GwtSV"

# 1. Busca os watchers do Nicolas Cage no banco
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("SELECT email FROM watches WHERE wiki_title = %s", ("Nicolas_Cage",))
rows = cur.fetchall()
print(f"Watchers encontrados: {rows}")

# Adiciona brainiackson@gmail.com se não estiver
cur.execute("""
    INSERT INTO watches (wiki_title, email, created_at)
    VALUES (%s, %s, NOW())
    ON CONFLICT DO NOTHING
""", ("Nicolas_Cage", "brainiackson@gmail.com"))
conn.commit()

# 2. Envia o email de simulação
resp = requests.post(
    "https://api.resend.com/emails",
    headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
    json={
        "from": "Mortivox <noreply@mortivox.com>",
        "to": ["brainiackson@gmail.com"],
        "subject": "ObituaryWatch: Nicolas Cage has died",
        "html": """
        <div style="background:#080808;color:#e8e4dc;font-family:'Courier New',monospace;padding:40px;max-width:600px;margin:0 auto">
          <h2 style="color:#c8b89a;letter-spacing:0.15em;text-transform:uppercase">Nicolas Cage</h2>
          <p style="color:#5a5650;font-size:13px;margin:8px 0 24px">Wikipedia death monitor — simulation test</p>
          <p style="font-size:15px;line-height:1.7">
            You requested to be notified when <strong style="color:#c8b89a">Nicolas Cage</strong> dies.<br><br>
            <em style="color:#5a5650">(This is a test simulation — Nicolas Cage is alive and well.)</em>
          </p>
          <a href="https://en.wikipedia.org/wiki/Nicolas_Cage"
             style="display:inline-block;margin-top:28px;color:#c8b89a;font-size:12px;letter-spacing:0.1em;text-transform:uppercase;text-decoration:none;border-bottom:1px solid #3a3428;padding-bottom:2px">
            View on Wikipedia →
          </a>
          <p style="margin-top:48px;font-size:11px;color:#3a3630;letter-spacing:0.1em">
            mortivox.com — know before everyone else
          </p>
        </div>
        """
    }
)
print(f"Email status: {resp.status_code} — {resp.text}")

cur.close()
conn.close()
