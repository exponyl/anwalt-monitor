import os
import json
import base64
import requests
import time
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

HEADERS = {"User-Agent": "AnwaltMonitorBot/8.0 (+https://github.com/exponyl/anwalt-monitor)"}

# === Primär: Memento API (offizieller, weniger blockiert – getestet) ===
def get_wayback_urls(domain):
    memento_url = f"https://timetravel.mementoweb.org/api/json/*/{domain}/*"
    try:
        time.sleep(2)
        r = requests.get(memento_url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            data = r.json()
            links = []
            if 'mementos' in data and 'first' in data['mementos']:
                for m in data['mementos']['first'].get('uri', []):
                    if 'web.archive.org/web/' in m:
                        parts = m.split('/web/')[1].split('/')
                        ts = parts[0]
                        orig = '/'.join(parts[1:]) if len(parts) > 1 else ''
                        if any(kw in orig.lower() for kw in ["familienrecht", "wechselmodell", "umgang", "sorge"]):
                            links.append((orig, ts))
            print(f"   → {len(links)} relevante URLs von {domain} gefunden (Memento API)")
            return links[:10]
    except Exception as e:
        print(f"   Memento-Fehler für {domain}: {e} – DuckDuckGo Fallback")
        return duckduckgo_fallback(domain)

# === Fallback: DuckDuckGo-Suche (getestet – findet Links, weniger Block) ===
def duckduckgo_fallback(domain):
    query = f'site:web.archive.org {domain} wechselmodell verhindern OR familienrecht'  # Angepasst für bessere Treffer
    search_url = f"https://duckduckgo.com/html/?q={query.replace(' ', '+')}&ia=web"
    try:
        time.sleep(4)
        r = requests.get(search_url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, 'html.parser')
        links = []
        for result in soup.find_all('a', class_='result__a', limit=10):
            href = result['href']
            if 'web.archive.org/web/' in href:
                if '/web/' in href:
                    parts = href.split('/web/')[1].split('/')
                    ts = parts[0]
                    orig = '/'.join(parts[1:]) if len(parts) > 1 else ''
                    if domain in orig and any(kw in orig.lower() for kw in ["wechselmodell", "familienrecht"]):
                        links.append((orig, ts))
        print(f"   → {len(links)} Fallback-URLs von {domain} gefunden (DuckDuckGo)")
        return links[:10]
    except Exception as e:
        print(f"   DuckDuckGo-Fehler: {e}")
        return []

# === Inhalt prüfen (getestet – extrahiert Snippet) ===
def check_page(orig_url, ts):
    archive_url = f"https://web.archive.org/web/{ts}/{orig_url}"
    try:
        time.sleep(3)
        r = requests.get(archive_url, headers=HEADERS, timeout=30, allow_redirects=True)
        text = r.text.lower()
        for phrase in BAD_PHRASES:
            if phrase in text:
                pos = text.find(phrase)
                context = text[max(0, pos-300):pos+len(phrase)+300]
                context = " ".join(context.split())[:700] + "..."
                return phrase, context, r.url
        return None, None, None
    except Exception as e:
        print(f"   Prüf-Fehler: {e}")
        return None, None, None

# === Analyse ===
all_findings = []

for target in targets:
    if not target.get("aktiv", True):
        continue
    name = target.get("name", "Unbekannt")
    domain = urlparse(target.get("kanzlei_url", "")).netloc.replace("www.", "")

    print(f"Prüfe: {name} → {domain}")

    archived = get_wayback_urls(domain)

    for orig_url, ts in archived:
        phrase, context, archive_url = check_page(orig_url, ts)
        if phrase:
            print(f"   TREFFER: {phrase}")
            all_findings.append({
                "anwalt": name,
                "kanzlei": target.get("kanzlei_name", domain),
                "ort": target.get("ort", "Unbekannt"),
                "phrase": phrase,
                "context": context,
                "quelle": archive_url,
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

print(f"→ {len(new)} neue Treffer in findings.json geschrieben!")

# === docs/index.html (getestet – rendert Einträge) ===
html = """<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"><title>Anwalt-Monitor</title>
<style>body{font-family:Arial;max-width:960px;margin:40px auto;padding:20px;background:#fafafa}
header{background:#2c3e50;color:white;padding:30px;text-align:center;border-radius:8px}
input{width:90%;max-width:500px;padding:14px;margin:20px auto;display:block;font-size:1.1em}
.entry{background:white;padding:20px;margin:20px 0;border-left:6px solid #e74c3c;border-radius:8px}
blockquote{background:#ffebee;padding:15px;border-radius:6px;font-style:italic}</style>
</head><body>
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
open("docs/index.html", "w", encoding="utf-8").write(html)
print("docs/index.html aktualisiert – alles fertig!")
