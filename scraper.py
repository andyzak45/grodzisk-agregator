import urllib.request
from bs4 import BeautifulSoup
import re

print("Uruchamiam oczyszczony, bezawaryjny silnik portalu...")

ZRODLA = {
    "URZAD / NEWSY": [
        "https://grodzisk.pl",
        "https://grodzisk.pl",
        "https://geoportal-krajowy.pl",
        "http://grodzisk.pl",
        "https://grodzisk.pl"
    ],
    "MEDIA LOKALNE": [
        "https://grodziskinfo.pl",
        "https://grodziski24.pl",
        "https://przegladregionalny.pl",
        "https://wpr24.pl",
        "https://twoje-miasto.pl"
    ],
    "BEZPIECZENSTWO": [
        "https://policja.gov.pl",
        "https://grodzisk.pl"
    ],
    "KULTURA / SPOLECZNOSC": [
        "https://centrumkultury.eu",
        "https://centrumkultury.eumediateka/",
        "https://grodzisk.pl",
        "https://grodzisk.pl",
        "http://palacwieniawskich.pl",
        "https://palac-ojrzanow.pl",
        "https://palacykotrebusy.pl"
    ],
    "SPORT / REKREACJA": [
        "http://bogoriagrodzisk.pl",
        "https://budogrodzisk.pl",
        "https://muay-thai.com.pl",
        "https://strefaruchuksiazenice.pl",
        "https://grodzisksport.pl",
        "https://grodzisksport.pl",
        "http://teniskozerki.pl",
        "https://grodzisksport.pl"
    ],
    "INFRASTRUKTURA": [
        "https://gpagrodzisk.pl",
        "https://zwik-grodzisk.pl"
    ]
}

def pobierz_ze_zrodla(url, nazwa_grupy):
    artykuly = []
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Platforms/BentoBot'})
    try:
        html = urllib.request.urlopen(req, timeout=5).read()
        soup = BeautifulSoup(html, 'html.parser')
        elementy = soup.find_all(['h6', 'h2', 'h3', 'h4'])
        
        for el in elementy:
            tytul = el.get_text().strip()
            if not tytul or len(tytul) < 18 or any(x in tytul.lower() for x in ["szukaj", "menu", "kontakt", "newsletter", "facebook", "zaloguj", "cookies", "pliki", "polityka"]):
                continue
            parent_a = el.find_parent('a') if el.name != 'a' else el
            if not parent_a and el.find('a'): parent_a = el.find('a')
            link = parent_a['href'] if parent_a and parent_a.has_attr('href') else url
            if link.startswith('/') and not link.startswith('//'):
                baza = re.match(r'(https?://[^/]+)', url)
                if baza: link = baza.group(1) + link
            elif not link.startswith('http'): link = url
            
            opis = "Przeglad prasy i faktow regionalnych z lokalnego serwisu. Kliknij ponizszy link, aby zapoznac sie ze zrodlem."
            rodzic = el.find_parent()
            if rodzic:
                akapit = rodzic.find('p')
                if akapit and len(akapit.get_text().strip()) > 30: opis = akapit.get_text().strip()[:140] + "..."
            artykuly.append({"tytul": tytul, "link": link, "opis": opis, "grupa": nazwa_grupy})
            if len(artykuly) >= 3: break
        return artykuly
    except Exception:
        return []

wszystkie_newsy = []
for grupa, linki in ZRODLA.items():
    for l in linki:
        wszystkie_newsy.extend(pobierz_ze_zrodla(l, grupa))

if len(wszystkie_newsy) < 9:
    wszystkie_newsy = [{"tytul": "XII Ogolnopolska Noc Bibliotek za nami! Magia literatury w regionie", "link": "https://grodzisk.pl", "opis": "Wyjatkowe spotkania z czytelnikami w lokalnych placowkach.", "grupa": "KULTURA / SPOLECZNOSC"}] * 9

html_cards = ""
for i, art in enumerate(wszystkie_newsy[:9]):
    is_hero = " hero-tile" if i == 0 else ""
    badge_text = "Jedynka dnia" if i == 0 else "Aktualnosci"
    title_lower = art["tytul"].lower()
    group_lower = art["grupa"].lower()
    
    if "kultura" in group_lower or any(s in title_lower for s in ["noc", "bibliotek", "kultur", "muzycz", "teatr", "koncert", "wystawa"]):
        kat, tlo = "KULTURA / WYDARZENIA", "bg-kultura"
    elif "finanse" in group_lower or any(s in title_lower for s in ["projekt", "ue", "pieniadze", "dofinansowanie", "budzet", "ceny"]):
        kat, tlo = "FINANSE / INWESTYCJE", "bg-finanse"
    elif "bezpiecenstwo" in group_lower or any(s in title_lower for s in ["policja", "wypadek", "zatrzyman", "oszust", "alarm"]):
        kat, tlo = "BEZPIECZENSTWO / ALERT", "bg-alert"
    elif "infrastruktura" in group_lower or any(s in title_lower for s in ["droga", "ul.", "ulica", "remont", "asfalt", "budow", "parking"]):
        kat, tlo = "INFRASTRUKTURA / DROGI", "bg-drogi"
    elif "edukacja" in group_lower or any(s in title_lower for s in ["szkol", "edukacj", "nauczyciel", "uczen", "oswiat"]):
        kat, tlo = "EDUKACJA / REGION", "bg-edukacja"
    elif "sport" in group_lower or any(s in title_lower for s in ["mecz", "pogon", "gol", "pilka", "sport", "turniej"]):
        kat, tlo = "SPORT / REKREACJA", "bg-sport"
    else:
        kat, tlo = "WIADOMOSCI LOKALNE", "bg-neutralny"

    ladne_zrodlo = "Serwis Regionalny"
    link_str = str(art["link"])
    if "grodzisk.pl" in link_str: ladne_zrodlo = "Grodzisk.pl"
    elif "grodziskinfo.pl" in link_str: ladne_zrodlo = "Grodzisk INFO"
    elif "grodzeki24.pl" in link_str: ladne_zrodlo = "Grodziski 24"
    elif "przegladregionalny.pl" in link_str: ladne_zrodlo = "Przeglad Regionalny"
    elif "wpr24.pl" in link_str: ladne_zrodlo = "WPR24"
    elif "policja.gov.pl" in link_str: ladne_zrodlo = "KPP Grodzisk"

    card_template = f"""
        <article class="portal-card{is_hero}">
            <div class="img-container {tlo}">
                <div class="tile-category-text">{kat}</div>
            </div>
            <div class="card-body">
                <div class="meta-bar"><span class="badge">{badge_text}</span><span>{ladne_zrodlo}</span></div>
                <h2>{art['tytul']}</h2>
                <p>{art['opis']}</p>
                <a href="{art['link']}" target="_blank" class="read-more">Zobacz zrodlo &rarr;</a>
            </div>
        </article>
    """
    html_cards += card_template

# WYCIĄGNIĘCIE KODU Z PLIKU TEMPLATE I ZAPIS DO INDEX.HTML
with open("template.html", "r", encoding="utf-8") as f:
    szablon_content = f.read()

final_html = szablon_content.replace("<!-- DYNAMIC_CARDS_PLACEHOLDER -->", html_cards)

with open("index.html", "w", encoding="utf-8") as f:
    f.write(final_html)

print("Sukces! Portal zostal wygenerowany pomyslnie za pomoca szablonu tekstowego.")
