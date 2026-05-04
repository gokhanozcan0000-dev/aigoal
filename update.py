# v3.1 — Fixed match fetching with status filter + team crest URLs

import os
import re
import json
import requests
from datetime import datetime, timedelta

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY")

# League IDs and their corresponding variable names in index.html
LEAGUE_IDS = {
    "superlig": 322,          # Trendyol Süper Lig
    "lig1": 323,              # Trendyol 1. Lig
    "kupasi": 304,            # Ziraat Kupası
    "pl": 2021,               # Premier League
    "championship": 2016,     # EFL Championship
    "bundesliga": 2002,       # Bundesliga
    "seriea": 2019,           # Serie A
    "laliga": 2014,           # La Liga
    "ligue1": 2015,           # Ligue 1
    "eredivisie": 2003,       # Eredivisie
    "primeiraliga": 2017,     # Primeira Liga
    "brasileirao": 2013,      # Brasileirão
    "championsleague": 2001,  # UEFA Champions League
}

TR_MONTHS = {
    1:"Oca",2:"Şub",3:"Mar",4:"Nis",5:"May",6:"Haz",
    7:"Tem",8:"Ağu",9:"Eyl",10:"Eki",11:"Kas",12:"Ara"
}
TR_DAYS = {0:"Pzt",1:"Sal",2:"Çar",3:"Per",4:"Cum",5:"Cmt",6:"Paz"}
EN_DAYS = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}
EN_MONTHS = {
    1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
    7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"
}

def format_date(date_str):
    """2026-04-25 → {tr:'25 Nis Cum', en:'Fri 25 Apr'}"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        tr = f"{d.day} {TR_MONTHS[d.month]} {TR_DAYS[d.weekday()]}"
        en = f"{EN_DAYS[d.weekday()]} {d.day} {EN_MONTHS[d.month]}"
        return tr, en
    except:
        return "2026", "2026"

def get_fixtures():
    """
    Fetch upcoming matches from football-data.org API.
    
    Key Fix: Use status=SCHEDULED to get ONLY scheduled matches.
    This prevents missing fixtures when the API returns mixed statuses.
    """
    today = datetime.now()
    next_week = today + timedelta(days=8)
    date_from = today.strftime("%Y-%m-%d")
    date_to = next_week.strftime("%Y-%m-%d")
    matches = []
    headers = {"X-Auth-Token": FOOTBALL_API_KEY}
    
    for league_key, league_id in LEAGUE_IDS.items():
        url = f"https://api.football-data.org/v4/competitions/{league_id}/matches"
        
        # CRITICAL FIX: Add status=SCHEDULED filter
        params = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "status": "SCHEDULED"  # Only fetch upcoming/scheduled matches
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                matches_list = data.get("matches", [])
                
                print(f"✓ {league_key}: {len(matches_list)} scheduled matches found")
                
                for m in matches_list:
                    # Extract team crests (NEW)
                    home_crest = m.get("homeTeam", {}).get("crest", "")
                    away_crest = m.get("awayTeam", {}).get("crest", "")
                    
                    matches.append({
                        "league": league_key,
                        "home": m["homeTeam"]["name"],
                        "away": m["awayTeam"]["name"],
                        "home_crest": home_crest,  # NEW: Store crest URL
                        "away_crest": away_crest,  # NEW: Store crest URL
                        "date": m["utcDate"][:10],
                        "time": m["utcDate"][11:16],  # HH:MM UTC
                    })
            
            elif response.status_code == 429:
                print(f"⚠ {league_key}: Rate limited (429). Waiting or reducing requests.")
            
            else:
                print(f"✗ {league_key}: API error {response.status_code}")
                
        except requests.exceptions.Timeout:
            print(f"✗ {league_key}: Request timeout")
        except Exception as e:
            print(f"✗ {league_key}: Error - {str(e)}")
    
    return matches

def get_predictions(matches):
    """
    Call Anthropic API to generate AI predictions for matches.
    Now includes crest URLs in the request context.
    """
    if not matches:
        return []
    
    all_predictions = []
    by_league = {}
    
    for m in matches:
        league = m.get("league", "pl")
        by_league.setdefault(league, []).append(m)

    for league_key, league_matches in by_league.items():
        # Format match list (crests are stored but not sent in prompt to avoid token waste)
        match_list = "\n".join([
            f"{m['home']} vs {m['away']}"
            for m in league_matches
        ])
        
        prompt = f"""Asagidaki {league_key} ligi futbol maclari icin 6 farkli yapay zeka modelinin tahminlerini simule et.

Her model farkli bir tahmin yapmali. Sadece su seceneklerden birini sec:
MS 1, MS 2, MS 1X, MS X2, MS X, KG Var, KG Yok, 2.5 Ust, 2.5 Alt

Kurallar:
- Buyuk favori varsa modellerin cogu MS 1 veya MS 2 demeli
- Dengeli macta modeller farkli tahminler vermeli
- Hicbir zaman hepsini ayni yapma
- MS X veya KG Yok nadiren kullan

Maclar:
{match_list}

SADECE JSON dondur, markdown veya aciklama yazma:
[{{"home":"takim","away":"takim","league":"{league_key}","predictions":{{"chatgpt":"MS 1","gemini":"MS 1","grok":"MS 1X","copilot":"KG Var","claude":"MS 1","perplexity":"2.5 Ust"}}}}]"""

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-5",
                    "max_tokens": 4000,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=60
            )
            
            if response.status_code == 200:
                content = response.json()["content"][0]["text"].strip()
                
                # Clean JSON markdown
                content = re.sub(r'^```json\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                
                try:
                    preds = json.loads(content)
                    
                    # Map fixture data (date, time, crests) to predictions
                    fixture_map = {
                        (m["home"], m["away"]): m
                        for m in league_matches
                    }
                    
                    for p in preds:
                        key = (p.get("home", ""), p.get("away", ""))
                        if key in fixture_map:
                            fixture = fixture_map[key]
                            p["date"] = fixture["date"]
                            p["time"] = fixture["time"]
                            # NEW: Include crest URLs
                            p["home_crest"] = fixture.get("home_crest", "")
                            p["away_crest"] = fixture.get("away_crest", "")
                    
                    all_predictions.extend(preds)
                    print(f"✓ {league_key}: {len(preds)} predictions received")
                    
                except json.JSONDecodeError:
                    # Fallback: try extracting JSON array
                    json_match = re.search(r'\[.*\]', content, re.DOTALL)
                    if json_match:
                        try:
                            preds = json.loads(json_match.group())
                            all_predictions.extend(preds)
                            print(f"✓ {league_key}: {len(preds)} predictions (fallback parse)")
                        except:
                            print(f"✗ {league_key}: JSON parse failed")
                    else:
                        print(f"✗ {league_key}: No JSON found in response")
            else:
                print(f"✗ {league_key}: Anthropic API error {response.status_code}")
                
        except Exception as e:
            print(f"✗ {league_key}: Prediction error - {str(e)}")

    return all_predictions

def pred_to_badge(pred):
    """Map prediction text to badge class and English label."""
    mapping = {
        "MS 1":  ("b1",  "1"),
        "MS 2":  ("bx2", "2"),
        "MS X":  ("bdash", "X"),
        "MS 1X": ("b1x", "1X"),
        "MS X2": ("bx2", "X2"),
        "KG Var":  ("bkg", "BTTS"),
        "KG Yok":  ("ba", "No BTTS"),
        "2.5 Ust": ("bu",  "O2.5"),
        "2.5 Üst": ("bu",  "O2.5"),
        "2.5 Alt": ("ba",  "U2.5"),
    }
    return mapping.get(pred, ("bkg", pred))

def generate_match_js(m):
    """
    Generate JavaScript object for a match with predictions and crests.
    
    NEW: Includes team crest URLs for logo display.
    """
    p = m.get("predictions", {})
    date_raw = m.get("date", "")
    date_tr, date_en = format_date(date_raw) if date_raw and date_raw != "2026" else ("2026", "2026")
    time_raw = m.get("time", "")
    
    # Format crest URLs (optional, only include if available)
    home_crest = m.get("home_crest", "")
    away_crest = m.get("away_crest", "")
    crest_js = ""
    if home_crest or away_crest:
        crest_js = f",hc:'{home_crest}',ac:'{away_crest}'"  # hc=home_crest, ac=away_crest

    def fmt(ai):
        pred_tr = p.get(ai, "MS 1")
        c, en = pred_to_badge(pred_tr)
        return '{' + f'tr:"{pred_tr}",en:"{en}",c:"{c}"' + '}'

    match_obj = (
        f'{{home:"{m["home"]}",away:"{m["away"]}",'
        f'date:{{tr:"{date_tr}",en:"{date_en}"}},time:"{time_raw}",derbi:false'
        f'{crest_js},'
        f'p:{{chatgpt:{fmt("chatgpt")},gemini:{fmt("gemini")},'
        f'grok:{fmt("grok")},copilot:{fmt("copilot")},'
        f'claude:{fmt("claude")},perplexity:{fmt("perplexity")}}}}}'
    )
    return match_obj

def update_league_in_html(html, league_key, league_predictions):
    """
    Update league matches in index.html using robust bracket counting.
    
    Finds: league_key: { ... matches:[ ... ] } and replaces the [...] content.
    """
    if not league_predictions:
        print(f"  {league_key}: No predictions, skipping")
        return html

    # Find the league_key: { ... matches:[ position
    pattern = re.compile(
        r'(\b' + re.escape(league_key) + r'\s*:\s*\{.*?matches\s*:\s*\[)',
        re.DOTALL
    )
    match = pattern.search(html)
    if not match:
        print(f"  {league_key}: Not found in HTML")
        return html

    bracket_start = match.end()

    # Count brackets to find closing ]
    depth = 1
    pos = bracket_start
    while pos < len(html) and depth > 0:
        if html[pos] == '[':
            depth += 1
        elif html[pos] == ']':
            depth -= 1
        pos += 1
    bracket_end = pos

    # Generate new match entries
    new_matches = []
    for j, pred in enumerate(league_predictions):
        match_js = generate_match_js(pred)
        if j < len(league_predictions) - 1:
            new_matches.append(match_js + ',')
        else:
            new_matches.append(match_js)

    new_block = '\n' + '\n'.join(new_matches) + '\n    '

    # Update HTML
    new_html = html[:bracket_start] + new_block + html[bracket_end - 1:]
    print(f"  {league_key}: Updated with {len(league_predictions)} matches")
    return new_html

def main():
    print("=" * 60)
    print(f"AIGoal update.py v3.1 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)
    print("\nChanges in v3.1:")
    print("  • Fixed: Added status=SCHEDULED filter to match API")
    print("  • New: Team crest URLs now captured and stored")
    print("  • Improved: Better error handling and logging")
    print("=" * 60)

    print("\n[1/3] Fetching fixtures from football-data.org...")
    matches = get_fixtures()
    print(f"      → Total {len(matches)} matches found\n")

    if not matches:
        print("✗ No matches found. Check API key and league IDs.")
        return

    print("[2/3] Requesting AI predictions...")
    predictions = get_predictions(matches)
    print(f"      → Total {len(predictions)} predictions received\n")

    if not predictions:
        print("✗ No predictions received. Check Anthropic API key.")
        return

    print("[3/3] Updating index.html...")
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    by_league = {}
    for m in predictions:
        league = m.get("league", "pl")
        by_league.setdefault(league, []).append(m)

    for league_key in sorted(by_league.keys()):
        league_matches = by_league[league_key]
        html = update_league_in_html(html, league_key, league_matches)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("\n" + "=" * 60)
    print("✓ index.html updated successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
