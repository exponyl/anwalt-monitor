import os
import json
import base64
import requests
from datetime import datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# === Secret holen – wenn nicht vorhanden, minimaler Fallback für Tests ===
encrypted = os.getenv("TARGETS_ENCRYPTED")

if encrypted:
    try:
        targets = json.loads(base64.b64decode(encrypted).decode("utf-8"))
        print(f"{len(targets)} Ziele aus Secret geladen")
    except Exception as e:
        print(f"Secret kaputt: {e}")
        targets = []
else:
    print("Kein Secret gefunden → verwende Test-Liste")
    # Minimaler Test-Datensatz – nur für lokale Tests und falls Secret fehlt
    targets = [
        {
            "name": "Ralton Wendeluth",
            "kanzlei_name": "Kanzlei Wendelmuth – Familienrecht",
            "kanzlei_url": "https://www.wendelmuth.net",
            "ort": "München",
            "aktiv": True
        }
    ]

BAD_PHRASES = [
    "wechselmodell verhindern", "wechselmodell sabotieren",
    "umgang verweigern", "kindeswohlgefährdung vortäuschen", "falsche gewaltvorwürfe"
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def get_wayback_urls(domain):
    query = f'site:web.archive.org {domain} "wechselmodell verhindern" OR familienrecht'
    url = f"https://duckduckgo.com/html/?q={query.replace(' ', '+')}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, 'html.parser')
        links = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if "web.archive.org/web/" not in href:
                continue
            try:
                part = href.split("/web/")[1]
                ts = part[:14]
                orig = "/".join(part.split("/")[1:]).split("?")[0]
                if domain in orig.lower():
                    links.append((orig, ts))
            except:
                continue
        print(f"   → {len(links)} URLs via DuckDuckGo gefunden")
        return links[:6]
    except Exception as e:
        print(f"   DuckDuckGo-Fehler: {e}")
        return []

def extract_snippet(orig_url, ts):
    url = f"https://web.archive.org/web/{ts}/{orig_url}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=18)
        text = r.text.lower()
        for phrase in BAD_PHRASES:
            if phrase in text:
                i = text.find(phrase)
                ctx = text[max(0, i-300):i+len(phrase)+300]
                ctx = " ".join(ctx.split())[:650] + "..."
                return phrase, ctx
        return None, None
    except:
        return None, None

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

# === findings.json schreiben ===
os.makedirs("data", exist_ok=True)
path = "data/findings.json"

old = json.load(open(path, "r", encoding="utf-8")) if os.path.exists(path) else []
existing = {f.get("quelle") for f in old}
new = [f for f in all_findings if f["quelle"] not in existing]
old.extend(new)

with open(path, "w", encoding="utf-8") as f:
    json.dump(old[-500:], f, indent=2, ensure_ascii=False)

print(f"→ {len(new)} neue Treffer geschrieben")

# === docs/index.html (funktioniert jetzt garantiert) ===
html = '''<!DOCTYPE html>
<html lang="de">
<head>
<head>
  <meta charset="UTF-8">
  <title>Anwalt-Monitor</title>
  <style>
    body{font-family:Arial,sans-serif;max-width:960px;margin:40px auto;padding:20px;background:#fafafa;line-height:1.6}
    header{background:#2c0392b;color:white;padding:30px;text-align:center;border-radius:10px}
    input{width:90%;max-width:500px;padding:14px;margin:20px auto;display:block;font-size:1.1em;border-radius:8px;border:1px solid #ccc}
    .entry{background:white;padding:20px;margin:20px 0;border-left:6px solid #e74c3c;border-radius:8px;box-shadow:0 3px 8px rgba(0,0,0,0.1)}
    blockquote{background:#ffebee;padding:15px;border-radius:6px;margin:10px 0;font-style:italic}
    a{color:#c0392b}
  </style>
</head>
<body>
<header><h1>Anwalt-Monitor</h1><p>Öffentliche Archiv-Quellen (Wayback Machine)</p></header>
<input type="text" placeholder="Anwalt oder Phrase suchen…" onkeyup="filter()">
<div id="results">Lade Daten…</div>

<script>
fetch('data/findings.json?' + Date.now())
  .then(r => r.ok ? r.json() : [])
  .then(data => {
    const div = document.getElementById('results');
    div.innerHTML = '';
    if (!data.length) {
      div.innerHTML = '<p style="text-align:center;color:#777">Noch keine Treffer gefunden.</p>';
      return;
    }
    data.slice().reverse().forEach(e => {
      div.innerHTML += `<div class="entry">
        <strong>${e.anwalt}</strong> • ${e.kanzlei} • ${e.ort}<br>
        <a href="${e.quelle}" target="_blank">Quelle öffnen (Wayback Machine)</a> • ${e.datum}
        <blockquote>…${e.context}</blockquote>
      </div>`;
    });
  })
  .catch(() => div.innerHTML = '<p style="color:red">Ladefehler – Seite neu laden</p>');

function filter() {
  let term = document.querySelector('input').value.toLowerCase();
  document.querySelectorAll('.entry').forEach(el => {
    el.style.display = el.textContent.toLowerCase().includes(term) ? 'block' : 'none';
  });
}
</script>
</body>
</html>'''

os.makedirs("docs", exist_ok=True)
with open("docs/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("docs/index.html aktualisiert – Monitor bereit!")
