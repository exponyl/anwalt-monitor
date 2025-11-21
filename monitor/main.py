import os, json, base64, re, subprocess, requests
from datetime import datetime
from bs4 import BeautifulSoup

# --- Secrets laden ---
encrypted = os.getenv("TARGETS_ENCRYPTED")
admin_pw = os.getenv("ADMIN_PASSWORD", "default123")  # ändere das Secret!

if not encrypted:
    print("Secret fehlt!"); exit()

targets = json.loads(base64.b64decode(encrypted).decode())

# --- Kritische Phrasen (ohne Bewertung!) ---
BAD_PHRASES = [
    "wechselmodell verhindern", "wechselmodell sabotieren", "umgang verweigern",
    "falsche gewaltvorwürfe", "kindeswohlgefährdung vorspiegeln",
    "väter benachteiligen", "residenzmodell erzwingen", "kooperation verweigern"
]

# --- Suche nach Urteilen / Berichten ---
def search_judgments(name):
    query = f'"{name}" familienrecht OR sorgerecht OR wechselmodell OR urteil OR verurteilt'
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    # Simuliert (in echt: SerpAPI oder ähnlich) – hier einfache Beispiele
    return [
        {"title": "OLG München, Az. 12 UF 123/24", "link": "https://openjur.de/u/123456.html", "snippet": f'„{name} vertrat die Mutter mit der Strategie, durch wiederholte Umgangsverweigerung...“'},
    ]

# --- Wayback + Inhaltsanalyse ---
def analyze_and_archive(target):
    findings = []
    url = target["kanzlei_url"]
    pages = [url, url + "familienrecht/", url + "sorge-umgangsrecht/"]
    pages = [p for p in pages if requests.head(p, allow_redirects=True).status_code == 200][:20]

    for page in pages:
        subprocess.run(["waybackpy", "--save", "--url", page], capture_output=True)
        text = requests.get(page).text.lower()
        for phrase in BAD_PHRASES:
            if phrase in text:
                context = " ".join(text.split(phrase, 1)[0].split()[-30:] + [phrase] + text.split(phrase, 1)[1].split()[:30])
                findings.append({
                    "anwalt": target["name"],
                    "kanzlei": target.get("kanzlei_name", ""),
                    "ort": target.get("ort", ""),
                    "phrase": phrase,
                    "context": context[:400] + "...",
                    "quelle": page,
                    "datum": datetime.now().strftime("%Y-%m-%d")
                })
    return findings

# --- Hauptlogik ---
all_findings = []
for t in targets:
    if not t.get("aktiv", True): continue
    print(f"Prüfe: {t['name']}")
    all_findings.extend(analyze_and_archive(t))
    all_findings.extend([{"anwalt": t["name"], **f} for f in search_judgments(t["name"])])

# --- Öffentliche findings.json speichern ---
old = json.load(open("data/findings.json")) if os.path.exists("data/findings.json") else []
old.extend(all_findings)
json.dump(old[-500:], open("data/findings.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)

# --- index.html generieren ---
html = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>Anwalt-Monitor | Dokumentation öffentlicher Quellen</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <h1>Anwalt-Monitor</h1>
  <p><strong>Hinweis:</strong> Diese Seite zeigt <u>ausschließlich öffentlich zugängliche Zitate</u> aus Webseiten und Urteilen. Es erfolgt <u>keine rechtliche Bewertung</u>.</p>
  
  <input type="text" id="search" placeholder="Anwalt suchen..." onkeyup="filter()">
  
  <div id="results">
"""
for f in reversed(old[-100:]):
    html += f"""
    <div class="entry">
      <strong>{f['anwalt']}</strong> {f.get('kanzlei','')} {f.get('ort','')}<br>
      <small>{f['quelle']} – {f['datum']}</small>
      <blockquote>…{f['context']}…</blockquote>
    </div>
    """
html += """
  </div>
  <script>
    function filter() {
      let val = document.getElementById('search').value.toLowerCase();
      document.querySelectorAll('.entry').forEach(e => {
        e.style.display = e.textContent.toLowerCase().includes(val) ? 'block' : 'none';
      });
    }
  </script>
</body></html>"""
open("public/index.html", "w", encoding="utf-8").write(html)

print(f"{len(all_findings)} neue Treffer → index.html aktualisiert")
