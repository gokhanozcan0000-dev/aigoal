# v3.0

import os
import re
import json
import requests
from datetime import datetime, timedelta

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY")

LEAGUE_IDS = {
    "pl": 2021,
    "championship": 2016,
    "bundesliga": 2002,
    "seriea": 2019,
    "laliga": 2014,
    "ligue1": 2015,
    "eredivisie": 2003,
    "worldcup": 2000,
    "championsleague": 2001,
    "brasileirao": 2013,
}

# UTC saat farkı yok — site Türkiye saatiyle gösteriyor ama
# tarih bilgisi yeterli, saat ayrıca eklenebilir
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
    today = datetime.now()
    next_week = today + timedelta(days=8)
    date_from = today.strftime("%Y-%m-%d")
    date_to = next_week.strftime("%Y-%m-%d")
    matches = []
    headers = {"X-Auth-Token": FOOTBALL_API_KEY}
    for league_key, league_id in LEAGUE_IDS.items():
        url = f"https://api.football-data.org/v4/competitions/{league_id}/matches"
        params = {"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED"}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json().get("matches", [])
                print(f"{league_key}: {len(data)} mac bulundu.")
                for m in data:
                    matches.append({
                        "league": league_key,
                        "home": m["homeTeam"]["name"],
                        "away": m["awayTeam"]["name"],
                        "date": m["utcDate"][:10],
                        "time": m["utcDate"][11:16],  # HH:MM UTC
                    })
            else:
                print(f"{league_key}: API hatasi {response.status_code}")
        except Exception as e:
            print(f"{league_key}: istek hatasi: {e}")
    return matches

def get_predictions(matches):
    if not matches:
        return []
    all_predictions = []
    by_league = {}
    for m in matches:
        league = m.get("league", "pl")
        by_league.setdefault(league, []).append(m)

    for league_key, league_matches in by_league.items():
        match_list = "\n".join([f"{m['home']} vs {m['away']}" for m in league_matches])
        prompt = f"""Asagidaki {league_key} ligi futbol maclari icin 6 farkli yapay zeka modelinin tahminlerini simule et.

Her model farkli bir tahmin yapmali. Sadece su seceneklerden birini sec:
MS 1, MS 2, MS 1X, MS X2, KG Var, 2.5 Ust, 2.5 Alt

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
                # JSON backtick temizle
                content = re.sub(r'^```json\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                try:
                    preds = json.loads(content)
                    # date bilgisini fixtures'dan ekle
                    date_map = {(m["home"], m["away"]): m for m in league_matches}
                    for p in preds:
                        key = (p.get("home",""), p.get("away",""))
                        if key in date_map:
                            p["date"] = date_map[key]["date"]
                            p["time"] = date_map[key]["time"]
                    all_predictions.extend(preds)
                    print(f"{league_key}: {len(preds)} tahmin alindi.")
                except json.JSONDecodeError:
                    # JSON array'i bulmaya calis
                    json_match = re.search(r'\[.*\]', content, re.DOTALL)
                    if json_match:
                        try:
                            preds = json.loads(json_match.group())
                            all_predictions.extend(preds)
                            print(f"{league_key}: {len(preds)} tahmin alindi (fallback).")
                        except:
                            print(f"{league_key}: JSON parse hatasi.")
                    else:
                        print(f"{league_key}: JSON bulunamadi.")
            else:
                print(f"{league_key}: Anthropic API hatasi {response.status_code}")
        except Exception as e:
            print(f"{league_key}: tahmin hatasi: {e}")

    return all_predictions

def pred_to_badge(pred):
    mapping = {
        "MS 1":  ("b1",  "1"),
        "MS 2":  ("bx2", "2"),
        "MS X":  ("b1x", "X"),
        "MS 1X": ("b1x", "1X"),
        "MS X2": ("bx2", "X2"),
        "KG Var":  ("bkg", "BTTS"),
        "KG Yok":  ("bkg", "BTTS No"),
        "2.5 Ust": ("bu",  "O2.5"),
        "2.5 Üst": ("bu",  "O2.5"),
        "2.5 Alt": ("ba",  "U2.5"),
    }
    return mapping.get(pred, ("bkg", pred))

def generate_match_js(m):
    p = m.get("predictions", {})
    date_raw = m.get("date", "")
    date_tr, date_en = format_date(date_raw) if date_raw and date_raw != "2026" else ("2026", "2026")

    def fmt(ai):
        pred_tr = p.get(ai, "MS 1")
        c, en = pred_to_badge(pred_tr)
        return '{' + f'tr:"{pred_tr}",en:"{en}",c:"{c}"' + '}'

    return (
        f'      {{home:"{m["home"]}",away:"{m["away"]}",'
        f'date:{{tr:"{date_tr}",en:"{date_en}"}},time:"",derbi:false,\n'
        f'       p:{{chatgpt:{fmt("chatgpt")},gemini:{fmt("gemini")},'
        f'grok:{fmt("grok")},copilot:{fmt("copilot")},'
        f'claude:{fmt("claude")},perplexity:{fmt("perplexity")}}}}}'
    )

def update_league_in_html(html, league_key, league_predictions):
    """
    Regex ile league_key'in matches:[...] bloğunu bulup değiştirir.
    Derin bracket sayımı yaparak güvenilir şekilde çalışır.
    """
    if not league_predictions:
        print(f"{league_key}: tahmin yok, atlanıyor.")
        return html

    # league_key: { ... matches:[ ... ] } bloğunu bul
    # Önce league key'in başlangıç pozisyonunu bul
    pattern = re.compile(
        r'(\b' + re.escape(league_key) + r'\s*:\s*\{.*?matches\s*:\s*\[)',
        re.DOTALL
    )
    m = pattern.search(html)
    if not m:
        print(f"{league_key}: HTML'de bulunamadi.")
        return html

    # matches:[ 'nin sonu
    bracket_start = m.end()  # '[' karakterinin hemen sonrası

    # Bracket sayarak kapanan ']' bul
    depth = 1
    pos = bracket_start
    while pos < len(html) and depth > 0:
        if html[pos] == '[':
            depth += 1
        elif html[pos] == ']':
            depth -= 1
        pos += 1
    bracket_end = pos  # kapanan ']' nin bir sonrası

    # Yeni maç JS'lerini oluştur
    new_matches = []
    for j, pred in enumerate(league_predictions):
        match_js = generate_match_js(pred)
        if j < len(league_predictions) - 1:
            new_matches.append(match_js + ',')
        else:
            new_matches.append(match_js)

    new_block = '\n' + '\n'.join(new_matches) + '\n    '

    # HTML'i güncelle
    new_html = html[:bracket_start] + new_block + html[bracket_end - 1:]
    print(f"{league_key}: {len(league_predictions)} mac ile guncellendi.")
    return new_html

def main():
    print("=" * 50)
    print(f"AIGoal update.py v3.0 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    print("\nMaclar cekiliyor...")
    matches = get_fixtures()
    print(f"Toplam {len(matches)} mac bulundu.")

    if not matches:
        print("Mac bulunamadi, cikiliyor.")
        return

    print("\nTahminler aliniyor...")
    predictions = get_predictions(matches)
    print(f"Toplam {len(predictions)} tahmin alindi.")

    if not predictions:
        print("Tahmin alinamadi, cikiliyor.")
        return

    print("\nindex.html guncelleniyor...")
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    by_league = {}
    for m in predictions:
        league = m.get("league", "pl")
        by_league.setdefault(league, []).append(m)

    for league_key, league_matches in by_league.items():
        html = update_league_in_html(html, league_key, league_matches)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("\nindex.html basariyla guncellendi!")

if __name__ == "__main__":
    main()
