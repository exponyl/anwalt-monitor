import os
import json
import base64
import requests
from datetime import datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# === Secrets ===
encrypted = os.getenv("TARGETS_ENCRYPTED")
if not encrypted:
    print("FEHLER: Secret fehlt!")
    exit(1)

targets = json.loads(base64.b64decode(encrypted).decode("utf-8"))

BAD_PHRASES = [
    "wechselmodell verhindern", "wechselmodell sabotieren",
    "umgang verweigern", "kindeswohlgefährdung vortäuschen", "falsche gewaltvorwürfe"
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}

# === Dynamische Suche via DuckDuckGo (getestet – funktioniert in Actions, findet Wayback-Links) ===
def get_wayback_urls(domain):
    query = f'site:web.archive.org {domain} (wechselmodell verhindern OR familienrecht OR umgang OR sorge)'
    url = f"https://duckduckgo.com/html/?q={query.replace(' ', '+')}&ia=web"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, 'html.parser')
        links = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if "web.archive.org/web/" in href:
                try:
                    part = href.split("/web/")[1]
                    ts = part.split("/")[0]
                    orig = "/".join(part.split("/")[1:]).split("?")[0]
                    if domain in orig.lower():
                        links.append((orig, ts))
                except:
                    continue
        print(f"   → {len(links)} URLs von {domain} gefunden (DuckDuckGo)")
        return links[:5]
    except Exception as e:
        print(f"   DuckDuckGo-Fehler: {e}")
        return []

# === Snippet extrahieren (ohne Blocking – getestet) ===
def extract_snippet(orig_url, ts):
    archive_url = f"https://web.archive.org/web/{ts}/{orig_url}"
    try:
        r = requests.get(archive_url, headers=HEADERS, timeout=15, allow_redirects=True)
        text = r.text.lower()
        for phrase in BAD_PHRASES:
            if phrase in text:
                pos = text.find(phrase)
                context = text[max(0, pos-250):pos+len(phrase)+250]
                context = " ".join(context.split())[:600] + "..."
                return phrase, context
        return None, None
    except:
        return None, None

# === Analyse ===
all_findings = []

for target in targets:
    if not target.get("aktiv", True):
        continue
    name = target.get("name", "Unbekannt")
    domain = urlparse(target.get("kanzlei_url", "")).netloc.replace("www.", "")

    print(f"Prüfe: {name} → {domain}")

    urls = get_wayback_urls(domain)

    for orig_url, ts in urls:
        phrase, context = extract_snippet(orig_url, ts)
        if phrase:
            print(f"   TREFFER: {phrase}")
            all_findings.append({
                "anwalt": name,
                "kanzlei": target.get("kanzlei_name", domain),
                "ort": target.get("ort", "Unbekannt"),
                "phrase": phrase,
                "context": context,
                "quelle": f"https://web.archive.org/web/{ts}/{orig_url}",
                "datum": datetime.now().strftime("%Y-%m-%d")
            })

# === findings.json ===
os.makedirs("data", exist_ok=True)
path = "data/findings.json"

old = json.load(open(path, "r", encoding="utf-8")) if os.path.exists(path) else []
existing = {f.get("quelle") for f in old}
new = [f for f in all_findings if f["quelle"] not in existing]
old.extend(new)

with open(path, "w", encoding="utf-8") as f:
    json.dump(old[-500:], f, indent=2, ensure_ascii=False)

if not new:
    print("   → Keine neuen Treffer – prüfe Phrasen oder Query")
else:
    print(f"→ {len(new)} neue Treffer in findings.json geschrieben!")

# === docs/index.html (fixierter Pfad für GitHub Pages /docs) ===
html = '''<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <title>Anwalt-Monitor</title>
  <style>
    body{font-family:Arial;max-width:960px;margin:40px auto;padding:20px;background:#fafafa}
    header{background:#2c3e50;color:white;padding:30px;text-align:center;border-radius:8px}
    input{width:90%;max-width:500px;padding:14px;margin:20px auto;display:block;font-size:1.1em}
    .entry{background:white;padding:20px;margin:20px 0;border-left:6px solid #e74c3c;border-radius:8px;box-shadow:0 2px 5px rgba(0,0,0,0.1)}
    blockquote{background:#ffebee;padding:15px;border-radius:6px;font-style:italic;margin:10px 0}
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
    if (!d.length) { c.innerHTML = '<p style="text-align:center;color:#777">Noch keine Treffer.</p>'; return; }
    d.slice().reverse().forEach(i => {
      c.innerHTML += `<div class="entry">
        <strong>${i.anwalt}</strong> • ${i.kanzlei} • ${i.ort}<br>
        <a href="${i.quelle}" target="_blank">Wayback Machine</a> • ${i.datum}
        <blockquote>…${i.context}</blockquote>
      </div>`;
    });
    console.log('Findings geladen:', d.length, 'Einträge');
  })
  .catch(e => {
    document.getElementById('results').innerHTML = '<p style="color:red">Fehler beim Laden der Daten.</p>';
    console.error('Fetch Error:', e);
  });

function filter() {
  let term = document.querySelector('input').value.toLowerCase();
  document.querySelectorAll('.entry').forEach(e => {
    e.style.display = e.textContent.toLowerCase().includes(term) ? 'block' : 'none';
  });
}
</script>
</body>
</html>'''

os.makedirs("docs", exist_ok=True)
with open("docs/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("docs/index.html aktualisiert – alles fertig!")
