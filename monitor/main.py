import os
import json
import base64
import requests
from datetime import datetime
from urllib.parse import urlparse

# === Secrets ===
encrypted = os.getenv("TARGETS_ENCRYPTED")
if not encrypted:
    print("FEHLER: Secret TARGETS_ENCRYPTED fehlt!")
    exit(1)

try:
    targets = json.loads(base64.b64decode(encrypted).decode("utf-8"))
except Exception as e:
    print(f"Entschlüsselungsfehler: {e}")
    exit(1)

# === Kritische Phrasen ===
BAD_PHRASES = [
    "wechselmodell verhindern",
    "wechselmodell sabotieren",
    "umgang verweigern",
    "kindeswohlgefährdung vortäuschen",
    "falsche gewaltvorwürfe",
    "väter benachteiligen"
]

# === Wayback CDX – nur familienrecht-relevante Seiten holen ===
def get_relevant_wayback_urls(domain):
    url = "https://web.archive.org/cdx/search/cdx"
    params = {
        "url": f"*.{domain}/*",
        "fl": "original,timestamp",
        "filter": "statuscode:200",
        "collapse": "digest",
        "limit": "500",
        "output": "json"
    }
    try:
        r = requests.get(url, params=params, timeout=25)
        data = r.json()
        if len(data) <= 1:
            return []
        results = []
        for item in data[1:]:
            orig = item[0]
            if any(kw in orig.lower() for kw in ["familienrecht", "wechselmodell", "umgang", "sorge", "scheidung"]):
                results.append((orig, item[1]))
        return results[:50]  # max 50 Seiten
    except Exception as e:
        print(f"CDX-Fehler: {e}")
        return []

# === Prüfen, ob kritische Phrase enthalten ist ===
def check_page(orig_url, timestamp):
    archive_url = f"https://web.archive.org/web/{timestamp}/{orig_url}"
    try:
        r = requests.get(archive_url, timeout=15)
        text = r.text.lower()
        for phrase in BAD_PHRASES:
            if phrase in text:
                pos = text.find(phrase)
                context = text[max(0, pos-200):pos+len(phrase)+200]
                context = " ".join(context.split())[:500] + "..."
                return phrase, context, archive_url
        return None, None, None
    except:
        return None, None, None

# === Hauptanalyse ===
all_findings = []

for target in targets:
    if not target.get("aktiv", True):
        continue

    name = target.get("name", "Unbekannt")
    url = target.get("kanzlei_url", "")
    domain = urlparse(url).netloc.replace("www.", "")

    print(f"Prüfe: {name} → {domain}")

    archived = get_relevant_wayback_urls(domain)
    print(f"   → {len(archived)} relevante archivierte Seiten gefunden")

    for orig_url, ts in archived:
        phrase, context, archive_url = check_page(orig_url, ts)
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

# === findings.json schreiben ===
os.makedirs("data", exist_ok=True)
path = "data/findings.json"
old = []
if os.path.exists(path):
    try:
        old = json.load(open(path, "r", encoding="utf-8"))
    except:
        pass

existing = {f.get("quelle") for f in old}
new = [f for f in all_findings if f["quelle"] not in existing]
old.extend(new)
final = old[-500:]

with open(path, "w", encoding="utf-8") as f:
    json.dump(final, f, indent=2, ensure_ascii=False)

print(f"→ {len(new)} neue Treffer in findings.json geschrieben!")

# === docs/index.html generieren (reine HTML-Datei, kein JS in f-String) ===
html_content = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Anwalt-Monitor | Öffentliche Quellen</title>
  <style>
    body{font-family:Arial,sans-serif;max-width:960px;margin:40px auto;padding:20px;background:#fafafa;color:#333;line-height:1.6}
    header{background:#2c3e50;color:white;padding:30px;text-align:center;border-radius:8px}
    h1{margin:0;font-size:2.2em}
    input{width:80%;max-width:500px;padding:14px;font-size:1.1em;margin:20px auto;display:block}
    .entry{background:white;padding:20px;margin:20px 0;border-left:6px solid #e74c3c;border-radius:8px;box-shadow:0 3px 10px rgba(0,0,0,0.1)}
    blockquote{background:#ffebee;padding:15px;border-radius:6px;font-style:italic}
  </style>
</head>
<body>
<header><h1>Anwalt-Monitor</h1><p>Öffentlich archivierte Quellen (Wayback Machine)</p></header>
<input type="text" placeholder="Nach Anwalt oder Stichwort suchen…" onkeyup="filter()">
<div id="results"><p style="text-align:center;color:#777">Lade Daten…</p></div>

<script>
fetch('../data/findings.json?t='+Date.now())
  .then(r => r.ok ? r.json() : [])
  .then(data => {
    const c = document.getElementById('results');
    c.innerHTML = '';
    if (data.length === 0) { c.innerHTML = '<p style="text-align:center;color:#777">Noch keine Treffer.</p>'; return; }
    data.slice().reverse().forEach(i => {
      c.innerHTML += `
        <div class="entry">
          <b>${i.anwalt}</b> • ${i.kanzlei} • ${i.ort}<br>
          <a href="${i.quelle}" target="_blank">Wayback Machine</a> • ${i.datum}
          <blockquote>…${i.context}</blockquote>
        </div>`;
    });
  });
function filter() {
  let term = document.querySelector('input').value.toLowerCase();
  document.querySelectorAll('.entry').forEach(e => {
    e.style.display = e.textContent.toLowerCase().includes(term) ? 'block' : 'none';
  });
}
</script>
</body>
</html>"""

os.makedirs("docs", exist_ok=True)
with open("docs/index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("docs/index.html erfolgreich erstellt – alles fertig!")
