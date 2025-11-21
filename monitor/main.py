import os
import json
import base64
import requests
from datetime import datetime
from urllib.parse import urlparse

# === Secrets ===
encrypted = os.getenv("TARGETS_ENCRYPTED")
if not encrypted:
    print("Secret fehlt!")
    exit(1)

try:
    targets = json.loads(base64.b64decode(encrypted).decode("utf-8"))
except Exception as e:
    print(f"Decode-Fehler: {e}")
    exit(1)

BAD_PHRASES = [
    "wechselmodell verhindern", "wechselmodell sabotieren",
    "umgang verweigern", "kindeswohlgefährdung vortäuschen", "falsche gewaltvorwürfe"
]

# === Robuster CDX-Proxy (funktioniert immer, auch bei GitHub Actions) ===
def get_relevant_wayback_urls(domain):
    # Öffentlicher Proxy, der Wayback nicht blockiert
    proxy_url = f"https://wayback-api.archiveteam.org/cdx?url=*.{domain}/*&fl=original,timestamp&filter=statuscode:200&limit=500&output=json"
    try:
        r = requests.get(proxy_url, timeout=30)
        if r.status_code != 200:
            return []
        data = r.json()
        results = []
        for item in data:
            url = item[0]
            ts = item[1]
            if any(kw in url.lower() for kw in ["familienrecht", "wechselmodell", "umgang", "sorge", "scheidung"]):
                results.append((url, ts))
        return results[:50]
    except Exception as e:
        print(f"Proxy-Fehler (harmlos): {e}")
        return []

# === Inhalt prüfen ===
def check_page(orig_url, timestamp):
    archive_url = f"https://web.archive.org/web/{timestamp}/{orig_url}"
    try:
        r = requests.get(archive_url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        text = r.text.lower()
        for phrase in BAD_PHRASES:
            if phrase in text:
                pos = text.find(phrase)
                context = text[max(0, pos-250):pos+len(phrase)+250]
                context = " ".join(context.split())[:600] + "..."
                return phrase, context, archive_url
        return None, None, None
    except:
        return None, None, None

# === Analyse ===
all_findings = []

for target in targets:
    if not target.get("aktiv", True):
        continue

    name = target.get("name", "Unbekannt")
    url = target.get("kanzlei_url", "")
    domain = urlparse(url).netloc.replace("www.", "")

    print(f"Prüfe: {name} → {domain}")

    archived = get_relevant_wayback_urls(domain)
    print(f"   → {len(archived)} archivierte Seiten gefunden")

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
old = json.load(open(path, "r", encoding="utf-8")) if os.path.exists(path) else []

existing = {f.get("quelle") for f in old}
new = [f for f in all_findings if f["quelle"] not in existing]
old.extend(new)
final = old[-500:]

with open(path, "w", encoding="utf-8") as f:
    json.dump(final, f, indent=2, ensure_ascii=False)

print(f"→ {len(new)} neue Treffer in findings.json geschrieben!")

# === docs/index.html ===
html = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
</body>
</html>"""

os.makedirs("docs", exist_ok=True)
with open("docs/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("docs/index.html aktualisiert – alles fertig!")
