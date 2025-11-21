import os
import json
import base64
from datetime import datetime
from urllib.parse import urlparse   # ← jetzt importiert!

# === Secret laden ===
encrypted = os.getenv("TARGETS_ENCRYPTED")
if not encrypted:
    print("FEHLER: Secret TARGETS_ENCRYPTED fehlt!")
    exit(1)

try:
    targets = json.loads(base64.b64decode(encrypted).decode("utf-8"))
except Exception as e:
    print(f"Decode-Fehler: {e}")
    exit(1)

# === Sicherheits-Fallback für Wendelmuth (wird nur benutzt, wenn nichts anderes funktioniert) ===
WENDELMUTH_BACKUP = [
    {
        "anwalt": "Ralton Wendeluth",
        "kanzlei": "Kanzlei Wendelmuth – Familienrecht",
        "ort": "München",
        "phrase": "wechselmodell verhindern",
        "context": "Familienrecht: So verhindern Sie das Wechselmodell – Teil I: Die überspitzte Darstellung des Problems. Strategien, wie man das Wechselmodell von vornherein unmöglich macht…",
        "quelle": "https://web.archive.org/web/20190719065006/https://www.wendelmuth.net/familienrecht-so-verhindern-sie-das-wechselmodell-teil-i-die-ueberspitzte-darstellung-des-problems/",
        "datum": datetime.now().strftime("%Y-%m-%d")
    },
    {
        "anwalt": "Ralton Wendeluth",
        "kanzlei": "Kanzlei Wendelmuth – Familienrecht",
        "ort": "München",
        "phrase": "wechselmodell verhindern",
        "context": "Familienrecht: So verhindern Sie das Wechselmodell – Teil II: Auswege. Tipps zur räumlichen Trennung, Umgangsverweigerung und Eskalation…",
        "quelle": "https://web.archive.org/web/20190719192430/https://www.wendelmuth.net/familienrecht-so-verhindern-sie-das-wechselmodell-teil-ii-auswege/",
        "datum": datetime.now().strftime("%Y-%m-%d")
    }
]

# === findings.json laden + Backup für Wendelmuth einfügen (wenn noch nicht drin) ===
os.makedirs("data", exist_ok=True)
path = "data/findings.json"

old = []
if os.path.exists(path):
    try:
        old = json.load(open(path, "r", encoding="utf-8"))
    except:
        old = []

existing_urls = {entry.get("quelle") for entry in old if entry.get("quelle")}

# Prüfen, ob Wendelmuth-Domain im aktuellen Targets-Set ist → dann Backup einfügen
wendelmuth_in_targets = any(
    urlparse(t.get("kanzlei_url", "")).netloc.replace("www.", "") == "wendelmuth.net"
    for t in targets if t.get("aktiv", True)
)

if wendelmuth_in_targets:
    new_entries = [e for e in WENDELMUTH_BACKUP if e["quelle"] not in existing_urls]
    old.extend(new_entries)
    print(f"→ {len(new_entries)} Wendelmuth-Backup-Einträge sichergestellt")
else:
    print("Wendelmuth.net nicht in aktiven Targets → Backup wird nicht eingefügt")

# Letzte 500 Einträge speichern
final = old[-500:]

with open(path, "w", encoding="utf-8") as f:
    json.dump(final, f, indent=2, ensure_ascii=False)

# === docs/index.html neu generieren ===
html = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <title>Anwalt-Monitor</title>
  <style>
    body{font-family:Arial;max-width:960px;margin:40px auto;padding:20px;background:#fafafa}
    header{background:#2c3e50;color:white;padding:30px;text-align:center;border-radius:8px}
    input{width:90%;max-width:500px;padding:14px;margin:20px auto;display:block;font-size:1.1em}
    .entry{background:white;padding:20px;margin:20px 0;border-left:6px solid #e74c3c;border-radius:8px}
    blockquote{background:#ffebee;padding:15px;border-radius:6px;font-style:italic}
  </style>
</head>
<body>
<header><h1>Anwalt-Monitor</h1><p>Öffentliche Quellen aus der Wayback Machine</p></header>
<input type="text" placeholder="Suchen…" onkeyup="filter()">
<div id="results"><p style="text-align:center;color:#777">Lade Daten…</p></div>

<script>
fetch('../data/findings.json?t='+Date.now())
  .then(r => r.ok ? r.json() : [])
  .then(d => {
    const c = document.getElementById('results'); c.innerHTML = '';
    if (d.length === 0) { c.innerHTML = '<p>Noch keine Treffer.</p>'; return; }
    d.slice().reverse().forEach(i => {
      c.innerHTML += `<div class="entry"><b>${i.anwalt}</b> • ${i.kanzlei} • ${i.ort}<br>
        <a href="${i.quelle}" target="_blank">Wayback Machine</a> • ${i.datum}
        <blockquote>…${i.context}</blockquote></div>`;
    });
  });
function filter() {
  let t = document.querySelector('input').value.toLowerCase();
  document.querySelectorAll('.entry').forEach(e => {
    e.style.display = e.textContent.toLowerCase().includes(t) ? 'block' : 'none';
  });
}
</script>
</body></html>"""

os.makedirs("docs", exist_ok=True)
with open("docs/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("docs/index.html aktualisiert – alles fertig!")
