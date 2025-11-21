import os
import json
import base64
import requests
from datetime import datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# --- Secrets ---
encrypted = os.getenv("TARGETS_ENCRYPTED")
if not encrypted:
    print("FEHLER: Secret TARGETS_ENCRYPTED fehlt!")
    exit(1)

try:
    targets = json.loads(base64.b64decode(encrypted).decode('utf-8'))
except:
    print("FEHLER beim Entschlüsseln der Targets!")
    exit(1)

# --- Kritische Phrasen ---
BAD_PHRASES = [
    "wechselmodell verhindern",
    "wechselmodell sabotieren",
    "umgangsverweigerung",
    "kindeswohlgefährdung vortäuschen",
    "falsche gewaltvorwürfe"
]

# --- Wayback CDX API: Alle archivierten URLs einer Domain finden ---
def get_wayback_urls(domain):
    url = f"http://web.archive.org/cdx/search/cdx"
    params = {
        'url': f"*.{domain}/*",
        'fl': 'original',
        'filter': 'statuscode:200',
        'collapse': 'digest',
        'limit': 1000,
        'output: 'json'
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()
        return [line[0] for line in data[1:]] if len(data) > 1 else []
    except:
        return []

# --- Prüfe, ob eine archivierte Seite kritische Phrasen enthält
def check_page_for_phrases(archive_url):
    try:
        r = requests.get(archive_url, timeout=15)
        text = r.text.lower()
        for phrase in BAD_PHRASES:
            if phrase in text:
                start = max(0, text.find(phrase) - 150)
                end = text.find(phrase) + len(phrase) + 150
                context = text[start:end].replace('\n', ' ').strip()
                return phrase, context[:400] + "..." if len(context) > 400 else context
        return None, None
    except:
        return None, None

# --- Hauptanalyse pro Target ---
all_findings = []

for target in targets:
    if not target.get("aktiv", True):
        continue

    name = target.get("name", "Unbekannt")
    url = target.get("kanzlei_url", "")
    domain = urlparse(url).netloc.replace("www.", "")

    print(f"Prüfe: {name} ({domain})")

    # 1. Alle archivierten Seiten dieser Domain via CDX API holen
    archived_urls = get_wayback_urls(domain)

    for orig_url in archived_urls:
        # Finde den neuesten verfügbaren Snapshot
        snap_url = f"https://web.archive.org/web/*/{orig_url}"
        phrase, context = check_page_for_phrases(snap_url.replace("/*/", "/20240000000000*/"))

        if phrase:
            # Finde einen echten Timestamp-Snapshot (nimm den ersten verfügbaren)
            try:
                test_snap = requests.head(f"https://web.archive.org/web/2/{orig_url}", allow_redirects=True)
                real_snap = test_snap.url if test_snap.status_code == 200 else snap_url
            except:
                real_snap = snap_url

            all_findings.append({
                "anwalt": name,
                "kanzlei": target.get("kanzlei_name", domain),
                "ort": target.get("ort", "Unbekannt"),
                "phrase": phrase,
                "context": context,
                "quelle": real_snap,
                "datum": datetime.now().strftime("%Y-%m-%d")
            })

# --- findings.json speichern ---
os.makedirs("data", exist_ok=True)
file_path = "data/findings.json"
old_findings = []
if os.path.exists(file_path):
    try:
        old_findings = json.load(open(file_path, encoding="utf-8"))
    except:
        pass

# Duplikate vermeiden
existing_urls = {item["quelle"] for item in old_findings}
new_unique = [f for f in all_findings if f["quelle"] not in existing_urls]

old_findings.extend(new_unique)
final_findings = old_findings[-500:]  # max. 500 Einträge

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(final_findings, f, indent=2, ensure_ascii=False)

print(f"{len(new_unique)} neue Treffer gefunden und gespeichert.")

# --- index.html in /docs generieren ---
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
  <strong>Hinweis:</strong> Nur öffentlich archivierte Inhalte. Keine Bewertung.
</div>
<div id="results">Lade Daten…</div>
<footer>Stand: <span id="date"></span></footer>

<script>
fetch('../data/findings.json?t='+Date.now())
  .then(r => r.json())
  .then(data => {
    const c = document.getElementById('results');
    c.innerHTML = '';
    if(data.length===0) c.innerHTML = '<p style="text-align:center;color:#777">Noch keine Treffer.</p>';
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
function filter(){ /* wie vorher */ 
  let t=document.getElementById('search').value.toLowerCase();
  document.querySelectorAll('.entry').forEach(e=>e.style.display=e.textContent.toLowerCase().includes(t)?'block':'none');
}
document.getElementById('date').textContent = new Date().toLocaleDateString('de-DE');
</script>
</body>
</html>"""

os.makedirs("docs", exist_ok=True)
open("docs/index.html", "w", encoding="utf-8").write(html)

print("index.html aktualisiert – bereit für GitHub Pages (/docs)")
