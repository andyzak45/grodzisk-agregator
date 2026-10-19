import urllib.request
from bs4 import BeautifulSoup

print("Uruchamiam bota portalu. Pobieram 6 najnowszych artykułów ze zdjęciami...")

url = "https://grodzisk.pl"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

try:
    html = urllib.request.urlopen(req).read()
    soup = BeautifulSoup(html, 'html.parser')
    naglowki = soup.find_all('h6')
    
    artykuly = []
    # Pobieramy 6 artykułów
    for h6 in naglowki[:6]:
        tytul = h6.get_text().strip()
        parent_a = h6.find_parent('a')
        link = parent_a['href'] if parent_a and parent_a.has_attr('href') else "https://grodzisk.pl"
        if not link.startswith('http'):
            link = "https://grodzisk.pl" + link
            
        # INTELIGENTNY DOBÓR ZDJĘĆ
        tytul_lower = tytul.lower()
        if any(slowo in tytul_lower for slowo in ["noc", "bibliotek", "muzyczny", "sejmik", "kultur", "kino"]):
            foto = "https://unsplash.com"
        elif any(slowo in tytul_lower for slowo in ["projekt", "ue", "pieniądze", "dofinansowanie", "budżet"]):
            foto = "https://unsplash.com"
        elif any(slowo in tytul_lower for slowo in ["plan", "przestrzen", "gminy", "ogólny", "mapa"]):
            foto = "https://unsplash.com"
        elif any(slowo in tytul_lower for slowo in ["droga", "ul.", "ulica", "remont", "asfalt", "budow", "oświetlenie", "monitoringu"]):
            foto = "https://unsplash.com"
        elif any(slowo in tytul_lower for slowo in ["szkoł", "edukacj", "nauczyciel", "uczeń", "narodowej"]):
            foto = "https://unsplash.com"
        else:
            foto = "https://unsplash.com"
            
        artykuly.append({"tytul": tytul, "link": link, "foto": foto})

    while len(artykuly) < 6:
        artykuly.append({"tytul": "Brak dodatkowych wiadomości na dziś", "link": "https://grodzisk.pl", "foto": "https://unsplash.com"})

    # BEZPIECZNE BUDOWANIE KAFELKÓW BEZ F-STRINGÓW DLA CAŁEGO BLOKU
    html_cards = ""
    for i, art in enumerate(artykuly):
        is_hero = " hero-tile" if i == 0 else ""
        badge_text = "Główny artykuł" if i == 0 else "Wiadomości"
        
        # Łączymy tekst bezpiecznie za pomocą tradycyjnej metody replace
        card_template = """
            <article class="portal-card[CLASS_PLACEHOLDER]">
                <div class="img-container"><img src="[FOTO_PLACEHOLDER]" alt="Foto"></div>
                <div class="card-body">
                    <div class="meta-bar"><span class="badge">[BADGE_PLACEHOLDER]</span><span>Grodzisk.pl</span></div>
                    <h2>[TYTUL_PLACEHOLDER]</h2>
                    <p>Automatyczny przegląd prasy lokalnej AI. Aktualne wiadomości i fakty wyciągnięte bezpośrednio z oficjalnych kanałów informacyjnych urzędu gminy pod kątem przydatności dla mieszkańców.</p>
                    <a href="[LINK_PLACEHOLDER]" target="_blank" class="read-more">Zobacz szczegóły &rarr;</a>
                </div>
            </article>
        """
        card_template = card_template.replace("[CLASS_PLACEHOLDER]", is_hero)
        card_template = card_template.replace("[FOTO_PLACEHOLDER]", art["foto"])
        card_template = card_template.replace("[BADGE_PLACEHOLDER]", badge_text)
        card_template = card_template.replace("[TYTUL_PLACEHOLDER]", art["tytul"])
        card_template = card_template.replace("[LINK_PLACEHOLDER]", art["link"])
        
        html_cards += card_template

    html_template = """<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Grodzisk & Książenice — Portal Informacyjny AI</title>
    <style>
        :root { 
            --bg-color: #f8fafc; 
            --card-bg: #ffffff; 
            --text-main: #0f172a; 
            --text-muted: #475569; 
            --accent: #2563eb;
            --border-radius: 16px; 
        }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            background-color: var(--bg-color); 
            color: var(--text-main); 
            margin: 0; 
            padding: 0; 
            line-height: 1.5;
        }
        header { 
            background-color: var(--card-bg); 
            border-bottom: 1px solid #e2e8f0; 
            padding: 1.5rem 2rem; 
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        .header-container { 
            max-width: 1300px; 
            margin: 0 auto; 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
        }
        h1 { margin: 0; font-size: 1.6rem; font-weight: 900; letter-spacing: -0.05em; }
        h1 span { color: var(--accent); }
        
        main { max-width: 1300px; margin: 2.5rem auto; padding: 0 1.5rem; }
        
        .magazine-grid { 
            display: grid; 
            grid-template-columns: repeat(3, 1fr);
            gap: 1.5rem; 
            width: 100%;
        }
        
        .portal-card { 
            background-color: var(--card-bg); 
            border-radius: var(--border-radius); 
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03);
            border: 1px solid #e2e8f0; 
            overflow: hidden; 
            display: flex; 
            flex-direction: column; 
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .portal-card:hover { 
            transform: translateY(-4px); 
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);
        }
        
        .hero-tile {
            grid-column: span 2;
        }
        .hero-tile .img-container {
            height: 320px;
        }
        .hero-tile h2 {
            font-size: 1.75rem;
        }

        .img-container {
            width: 100%;
            height: 180px;
            overflow: hidden;
            position: relative;
            background-color: #cbd5e1;
        }
        .img-container img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.5s ease;
        }
        .portal-card:hover .img-container img {
            transform: scale(1.03);
        }
        
        .card-body { padding: 1.5rem; display: flex; flex-direction: column; flex-grow: 1; }
        .meta-bar { display: flex; align-items: center; gap: 0.75rem; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.75rem; }
        .badge { background-color: #eff6ff; color: var(--accent); padding: 0.25rem 0.6rem; border-radius: 6px; font-weight: 700; font-size: 0.75rem; text-transform: uppercase; }
        
        h2 { margin: 0 0 0.75rem 0; font-size: 1.25rem; font-weight: 800; line-height: 1.3; color: #0f172a; letter-spacing: -0.02em; }
        p { color: #334155; font-size: 0.95rem; margin: 0 0 1.5rem 0; text-align: justify; }
        .read-more { color: var(--accent); text-decoration: none; font-weight: 700; font-size: 0.9rem; margin-top: auto; display: inline-flex; align-items: center; gap: 0.25rem; }
        
        @media (max-width: 968px) {
            .magazine-grid { grid-template-columns: 1fr; }
            .hero-tile { grid-column: span 1; }
            .hero-tile .img-container { height: 200px; }
        }
        
        footer { 
            text-align: center; 
            padding: 3rem 1rem; 
            color: var(--text-muted); 
            font-size: 0.85rem; 
            border-top: 1px solid #e2e8f0; 
            margin-top: 6rem; 
            background-color: #ffffff; 
        }
    </style>
</head>
<body>
    <header>
        <div class="header-container">
            <h1>Grodzisk&Książenice<span>.bento</span></h1>
            <div style="font-size: 0.85rem; font-weight: 600; color: var(--text-muted);">Wydanie Cyfrowe AI</div>
        </div>
    </header>
    <main>
        <div class="magazine-grid">
            <!-- DYNAMIC_CARDS_PLACEHOLDER -->
        </div>
    </main>
    <footer>
        <p>Grodzisk & Książenice Magazyn Bento © 2026. Portal aktualizowany automatycznie przez bota w Pythonie.</p>
    </footer>
</body>
</html>
"""

    final_html = html_template.replace("<!-- DYNAMIC_CARDS_PLACEHOLDER -->", html_cards)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(final_html)
        
    print("Sukces! Wygenerowałem portal ze zdjęciami.")

except Exception as e:
    print(f"Coś poszło nie tak: {e}")
