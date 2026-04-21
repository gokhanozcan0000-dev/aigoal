# Weekly auto-update script

import os
import json
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
            for m in response.json().get("matches", []):
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
    all_predictions = []
    by_league = {}
    for m in matches:
        league = m.get("league", "pl")
        if league not in by_league:
            by_league[league] = []
        by_league[league].append(m)
    for league_key, league_matches in by_league.items():
        match_list = "\n".join([f"{m['home']} vs {m['away']}" for m in league_matches])
        prompt = f"""Asagidaki futbol maclari icin 6 farkli yapay zeka modelinin tahminlerini simule et.
Tahmin secenekleri: MS 1, MS X, MS 2, MS 1X, MS X2, KG Var, KG Yok, 2.5 Ust, 2.5 Alt

Maclar ({league_key}):
{match_list}

SADECE JSON dondur, baska hicbir sey yazma:
[{{"home":"takim","away":"takim","league":"{league_key}","date":"2026","predictions":{{"chatgpt":"TAHMIN","gemini":"TAHMIN","grok":"TAHMIN","copilot":"TAHMIN","claude":"TAHMIN","perplexity":"TAHMIN"}}}}]"""
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-opus-4-7",
                "max_tokens": 4000,
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        if response.status_code == 200:
            content = response.json()["content"][0]["text"]
            try:
                preds = json.loads(content)
                all_predictions.extend(preds)
                print(f"{league_key}: {len(preds)} tahmin alindi.")
            except:
                import re
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    try:
                        preds = json.loads(json_match.group())
                        all_predictions.extend(preds)
                        print(f"{league_key}: {len(preds)} tahmin alindi.")
                    except:
                        print(f"{league_key}: parse hatasi.")
                else:
                    print(f"{league_key}: JSON bulunamadi.")
        else:
            print(f"{league_key}: API hatasi {response.status_code}")
    return all_predictions

def pred_to_badge(pred):
    mapping = {
        "MS 1": ("b1", "1"), "MS X": ("b1x", "X"), "MS 2": ("bx2", "2"),
        "MS 1X": ("b1x", "1X"), "MS X2": ("bx2", "X2"),
        "KG Var": ("bkg", "BTTS"), "KG Yok": ("bkg", "BTTS No"),
        "2.5 Ust": ("bu", "O2.5"), "2.5 Alt": ("ba", "U2.5"),
        "2.5 \u00dcst": ("bu", "O2.5"),
    }
    return mapping.get(pred, ("bkg", pred))

def generate_match_js(m):
    p = m.get("predictions", {})
    date_str = m.get("date", "2026")
    def fmt(ai):
        pred_tr = p.get(ai, "MS 1")
        c, en = pred_to_badge(pred_tr)
        return '{' + f'tr:"{pred_tr}",en:"{en}",c:"{c}"' + '}'
    return (
        f'      {{home:"{m["home"]}",away:"{m["away"]}",'
        f'date:{{tr:"{date_str}",en:"{date_str}"}},time:"",derbi:false,\n'
        f'       p:{{chatgpt:{fmt("chatgpt")},gemini:{fmt("gemini")},'
        f'grok:{fmt("grok")},copilot:{fmt("copilot")},'
        f'claude:{fmt("claude")},perplexity:{fmt("perplexity")}}}}}'
    )

def update_league_in_html(html, league_key, league_predictions):
    if not league_predictions:
        return html
    
    lines = html.split('\n')
    new_lines = []
    i = 0
    updated = False
    
    while i < len(lines):
        line = lines[i]
        # League key satırını bul
        if (f'  {league_key}:' in line or f'\t{league_key}:' in line or 
            line.strip().startswith(f'{league_key}:')):
            # matches:[ satırını ara
            new_lines.append(line)
            i += 1
            while i < len(lines):
                new_lines.append(lines[i])
                if 'matches:[' in lines[i] or 'matches: [' in lines[i]:
                    i += 1
                    # Eski maçları atla
                    depth = 0
                    while i < len(lines):
                        l = lines[i]
                        if l.strip() == ']' or l.strip() == '],':
                            # Yeni maçları ekle
                            new_match_lines = []
                            for j, pred in enumerate(league_predictions):
                                match_js = generate_match_js(pred)
                                if j < len(league_predictions) - 1:
                                    new_match_lines.append(match_js + ',')
                                else:
                                    new_match_lines.append(match_js)
                            new_lines.extend(new_match_lines)
                            new_lines.append(l)
                            i += 1
                            updated = True
                            break
                        i += 1
                    break
                i += 1
        else:
            new_lines.append(line)
            i += 1
    
    if updated:
        print(f"{league_key}: guncellendi.")
    else:
        print(f"{league_key}: guncellenmedi.")
    
    return '\n'.join(new_lines)

def main():
    print("Maclar cekiliyor...")
    matches = get_fixtures()
    print(f"{len(matches)} mac bulundu.")
    if not matches:
        print("Mac bulunamadi, cikiliyor.")
        return
    print("Tahminler aliniyor...")
    predictions = get_predictions(matches)
    print(f"{len(predictions)} tahmin alindi.")
    if not predictions:
        print("Tahmin alinamadi, cikiliyor.")
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
        html = update_league_in_html(html, league_key, league_matches)
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print("index.html guncellendi!")

if __name__ == "__main__":
    main()
