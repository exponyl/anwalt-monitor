import os
import json
import base64
import requests
from datetime import datetime
from urllib.parse import urlparse

# --- Secrets laden ---
encrypted = os.getenv("TARGETS_ENCRYPTED")
if not encrypted:
    print("FEHLER: Secret TARGETS_ENCRYPTED fehlt!")
    exit(1)

try:
    targets = json.loads(base64.b64decode(encrypted).decode('utf-8'))
except Exception as e:
    print(f"FEHLER beim Entschlüsseln: {e}")
    exit(1)

# --- Kritische Phrasen ---
BAD_PHRASES = [
    "wechselmodell verhindern",
    "wechselmodell sabotieren",
    "umgang verweigern",
    "kindeswohlgefährdung vortäuschen",
    "falsche gewaltvorwürfe",
    "väter benachteiligen"
]

# --- Alle archivierten URLs einer Domain via Wayback CDX API holen ---
def get_wayback_urls(domain):
    cdx_url = "http://web.archive.org/cdx/search/cdx"
    params = {
        "url": f"*.{domain}/*",
        "fl": "original,timestamp",
        "filter": "statuscode:200",
        "collapse": "digest",
        "limit": "1000",
        "output": "json"
    }
    try:
        r = requests.get(cdx_url, params=params, timeout=30)
        data = r.json()
        if len(data) <= 1:
            return []
        return [(item[0], item[1]) for item in data[1:]]  # (original_url, timestamp)
    except Exception as e:
        print(f"CDX-Fehler für {domain}: {e}")
        return []

# --- Inhalt einer archivierten Seite prüfen ---
def check_archived_page(original_url, timestamp):
    archive_url = f"https://web.archive.org/web/{timestamp}/{original_url}"
    try:
        r = requests.get(archive_url, timeout=20)
        text = r.text.lower()
        for phrase in BAD_PHRASES:
            if phrase in text:
                start = max(0, text.find(phrase) - 200)
                end = text.find(phrase) + len(phrase) + 200
                context = text[start:end]
                context = " ".join(context.split())[:500] + "..."
                return phrase, context, archive_url
        return None, None, None
    except:
        return None, None, None

# --- Hauptanalyse ---
all_findings = []

for target in targets:
    if not target.get("aktiv", True):
        continue

    name = target.get("name", "Unbekannt")
    url = target.get("kanzlei_url", "")
    domain = urlparse(url).netloc.replace("www.", "")

    print(f"Prüfe Domain: {domain} ({name})")

    archived = get_wayback_urls(domain)
    print(f"   → {len(archived)} archivierte Seiten gefunden")

    for orig_url, ts in archived:
        phrase, context, archive_url = check_archived_page(orig_url, ts)
        if phrase:
            print(f"   → Treffer: {phrase}")
            all_findings.append({
                "anwalt": name,
                "kanzlei": target.get("kanzlei_name", domain),
                "ort": target.get("ort", "Unbekannt"),
                "phrase": phrase,
                "context": context,
                "quelle": archive_url,
                "datum": datetime.now().strftime("%Y-%m-%d")
            })

# --- findings.json speichern ---
os.makedirs("data", exist_ok=True)
file_path = "data/findings.json"
old = []
if os.path.exists(file_path):
    try:
        old = json.load(open(file_path, encoding="utf-8"))
    except:
        pass

# Duplikate vermeiden
existing = {f["quelle"] for f in old}
new_unique = [f for f in all_findings if f["quelle"] not in existing]
old.extend(new_unique)
final = old[-500:]

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(final, f, indent=2, ensure_ascii=False)

print(f"{len(new_unique)} neue Treffer gespeichert.")

# --- docs/index.html generieren (für GitHub Pages /docs) ---
html = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Anwalt-Monitor | Öffentliche Quellen</title>
  <style>
    body{font-family:Arial,sans-serif;max-width:960px;margin:40px auto;padding:20px;background:#fafafa;color:#333;line-height:1.6}
    header{text-align:center;padding:30px;background:#2c3e50;color:white;border-radius:8px}
    h1{margin:0;font-size:2.2em}
    .search{margin:30px 0;text-align:center}
    input[type=text]{width:80%;max-width:500px;padding:14px;font-size:1.1em;border:1px solid #ccc;border-radius:6px}
    .disclaimer{background:#fff3cd;padding:18px;border-radius:8px;margin:25px 0;font-size:0.95em}
    .entry{background:white;padding:20px;margin:20px 0;border-left:6px solid #e74c3c;box-shadow:0 3px 10px rgba(0,0,0,0.1);border-radius:8px}
    .name{font-size:1.4em;font-weight:bold;color:#2c3e50}
    .meta{font-size:0.9em;color:#666;margin:10px 0}
    blockquote{background:#ffebee;padding:15px;border-radius:6px;margin:15px 0;font-style:italic}
    footer{text-align:center;margin-top:60px;color:#777;font-size:0.9em}
  </style>
</head>
<body>
<header>
  <h1>Anwalt-Monitor</h1>
  <p>Dokumentation öffentlich zugänglicher Quellen im Familienrecht</p>
</header>
<div class="search">
  <input type="text" id="search" placeholder="Nach Anwalt oder Stichwort suchen…" onkeyup="filter()">
</div>
<div class="disclaimer">
  <strong>Wichtiger Hinweis:</strong> Nur öffentlich archivierte Inhalte aus der Wayback Machine. Es erfolgt <u>keine rechtliche Bewertung</u>.
</div>
<div id="results">
  <p style="text-align:center;color:#777;">Lade Daten…</p>
</div>
<footer>Stand: <span id="date"></span></footer>

<script>
fetch('../data/findings.json?t='+Date.now())
  .then(r => r.ok ? r.json() : [])
  .then(data => {
    const c = document.getElementById('results');
    c.innerHTML = '';
    if (data.length === 0) {
      c.innerHTML = '<p style="text-align:center;color:#777">Noch keine Treffer.</p>';
      return;
    }
    data.slice().reverse().forEach(i => {
      const d = document.createElement('div');
      d.className = 'entry';
      d.innerHTML = `
        <div class="name">${i.anwalt}</div>
        <div class="meta">${i.kanzlei} • ${i.ort} • <a href="${i.quelle}" target="_blank">Wayback Machine</a> • ${i.datum}</div>
        <blockquote>…${i.context}</blockquote>
      `;
      c.appendChild(d);
    });
  });
function filter() {
  const term = document.getElementById('search').value.toLowerCase();
  document.querySelectorAll('.entry').forEach(e => {
    e.style.display = e.textContent.toLowerCase().includes(term) ? 'block' : 'none';
  });
}
document.getElementById('date').textContent = new Date().toLocaleDateString('de-DE');
</script>
</body>
</html>"""

os.makedirs("docs", exist_ok=True)
open("docs/index.html", "w", encoding="utf-8").write(html)
print("docs/index.html erfolgreich aktualisiert")
