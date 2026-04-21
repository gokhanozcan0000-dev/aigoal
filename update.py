import os
import json
import base64
import requests
from datetime import datetime, timedelta

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY")

LEAGUE_IDS = {
    "pl": 2021,
    "bundesliga": 2002,
    "seriea": 2019,
    "laliga": 2014,
    "ligue1": 2015,
    "eredivisie": 2003,
}

def get_fixtures():
    today = datetime.now()
    next_week = today + timedelta(days=7)
    date_from = today.strftime("%Y-%m-%d")
    date_to = next_week.strftime("%Y-%m-%d")
    
    all_matches = []
    headers = {"X-Auth-Token": FOOTBALL_API_KEY}
    
    for league_key, league_id in LEAGUE_IDS.items():
        url = f"https://api.football-data.org/v4/competitions/{league_id}/matches"
        params = {"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED"}
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            matches = data.get("matches", [])
            for m in matches:
                all_matches.append({
                    "league": league_key,
                    "home": m["homeTeam"]["name"],
                    "away": m["awayTeam"]["name"],
                    "date": m["utcDate"][:10]
                })
    
    return all_matches

def get_predictions(matches):
    if not matches:
        return []
    
    match_list = "\n".join([f"{m['home']} vs {m['away']} ({m['league']})" for m in matches])
    
    prompt = f"""Sen bir futbol analiz uzmanısın. Aşağıdaki maçlar için 6 farklı yapay zeka modelinin (ChatGPT, Gemini, Grok, Copilot, Claude, Perplexity) tahminlerini simüle et.

Her model için gerçekçi ve birbirinden farklı tahminler üret. Tahmin seçenekleri: MS 1, MS X, MS 2, MS 1X, MS X2, KG Var, KG Yok, 2.5 Üst, 2.5 Alt

Maçlar:
{match_list}

Yanıtı SADECE aşağıdaki JSON formatında ver, başka hiçbir şey yazma:
[
  {{
    "home": "ev sahibi takım adı",
    "away": "deplasman takımı adı", 
    "league": "lig kodu",
    "date": "tarih",
    "predictions": {{
      "chatgpt": "TAHMİN",
      "gemini": "TAHMİN",
      "grok": "TAHMİN",
      "copilot": "TAHMİN",
      "claude": "TAHMİN",
      "perplexity": "TAHMİN"
    }}
  }}
]"""

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    
    if response.status_code == 200:
        content = response.json()["content"][0]["text"]
        try:
            return json.loads(content)
        except:
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
    return []

def pred_to_badge(pred):
    mapping = {
        "MS 1": ("b1", "1"),
        "MS X": ("b1x", "X"),
        "MS 2": ("bx2", "2"),
        "MS 1X": ("b1x", "1X"),
        "MS X2": ("bx2", "X2"),
        "KG Var": ("bkg", "BTTS"),
        "KG Yok": ("bkg", "BTTS No"),
        "2.5 Üst": ("bu", "O2.5"),
        "2.5 Alt": ("ba", "U2.5"),
    }
    return mapping.get(pred, ("bkg", pred))

def generate_match_js(predictions):
    if not predictions:
        return ""
    
    lines = []
    for m in predictions:
        p = m.get("predictions", {})
        date_str = m.get("date", "")
        
        def fmt(ai):
            pred_tr = p.get(ai, "MS 1")
            c, en = pred_to_badge(pred_tr)
            return f'{{tr:"{pred_tr}",en:"{en}",c:"{c}"}}'
        
        line = f'''      {{home:"{m["home"]}",away:"{m["away"]}",date:{{tr:"{date_str}",en:"{date_str}"}},time:"",derbi:false,
       p:{{chatgpt:{fmt("chatgpt")},gemini:{fmt("gemini")},grok:{fmt("grok")},copilot:{fmt("copilot")},claude:{fmt("claude")},perplexity:{fmt("perplexity")}}}}}'''
        lines.append(line)
    
    return ",\n".join(lines)

def update_league_in_html(html, league_key, new_matches_js):
    if not new_matches_js:
        return html
    
    import re
    pattern = rf"({re.escape(league_key)}:\s*{{[^}}]*matches:\s*\[)(.*?)(\s*\]\s*}})"
    
    def replacer(match):
        return match.group(1) + "\n" + new_matches_js + "\n    " + match.group(3)
    
    new_html = re.sub(pattern, replacer, html, flags=re.DOTALL)
    return new_html

def main():
    print("Maçlar çekiliyor...")
    matches = get_fixtures()
    print(f"{len(matches)} maç bulundu.")
    
    if not matches:
        print("Maç bulunamadı, çıkılıyor.")
        return
    
    print("Claude'dan tahminler alınıyor...")
    predictions = get_predictions(matches)
    print(f"{len(predictions)} tahmin alındı.")
    
    if not predictions:
        print("Tahmin alınamadı, çıkılıyor.")
        return
    
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    by_league = {}
    for m in predictions:
        league = m.get("league", "pl")
        if league not in by_league:
            by_league[league] = []
        by_league[league].append(m)
    
    for league_key, league_matches in by_league.items():
        new_js = generate_match_js(league_matches)
        html = update_league_in_html(html, league_key, new_js)
        print(f"{league_key}: {len(league_matches)} maç güncellendi.")
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print("index.html güncellendi!")

if __name__ == "__main__":
    main()
