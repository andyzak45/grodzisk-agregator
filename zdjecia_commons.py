"""Zbiera kandydatów na zdjęcia z Wikimedia Commons (wolne licencje) dla gminy i powiatu grodziskiego.

Uruchamiany ręcznie (workflow "Zbieranie zdjęć z Wikimedia Commons"). Niczego nie wstawia na stronę: zapisuje
  data/zdjecia_kandydaci.json  (pełne dane: autor, licencja, adresy)
  data/zdjecia_kandydaci.html  (arkusz przeglądowy z miniaturami; zaznaczasz zdjęcia, które nam pasują)
Zdjęcia wybiera człowiek: skrypt tylko odsiewa to, czego na pewno nie wolno użyć (licencje z NC, ND, brak licencji,
zbyt małe pliki, formaty inne niż JPEG i PNG) i oznacza ostrzeżenia (znaki towarowe, prawa osobiste).
Użycie: python zdjecia_commons.py [--tematy | --szukaj | --wsie | --tematy-auto]
  --tematy-auto: automatyczny wybór zdjęć ogólnych do 8 na temat (data/zdjecia_tematy.txt);
  --wsie: automatyczny wybór po 3 zdjęcia dla każdej miejscowości gminy (data/zdjecia_wsie.txt);
  --tematy: tylko zdjęcia ogólne do tematów;  --szukaj: pliki znalezione wyszukiwarką Commons po frazach o Grodzisku
"""
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://commons.wikimedia.org/w/api.php"
KONTAKT = os.environ.get("BOT_CONTACT") or "https://andyzak45.github.io/grodzisk-agregator/"
USER_AGENT = f"GrodziskLokalnieBot/1.0 (agregator lokalny; kontakt: {KONTAKT})"

# (fraza szukana wśród kategorii, wzorzec, który musi pasować do nazwy kategorii)
MIEJSCA = [
    ("Grodzisk Mazowiecki", r"grodzisk mazowiecki"),
    ("Milanówek", r"milan[óo]wek"),
    ("Podkowa Leśna", r"podkowa"),
    ("Jaktorów", r"jaktor[óo]w"),
    ("Żabia Wola", r"[żz]abia wola"),
    ("Baranów Grodzisk County", r"baran[óo]w.*(grodzisk|masovian|mazowieck)"),
]
# Zdjęcia ogólne (nie z naszej gminy) do wpisów, dla których nie ma zdjęcia miejsca: kategorie Commons wyszukiwane po frazie.
# Nazwa kategorii musi wskazywać Polskę, żeby nie wpadły zdjęcia z całego świata.
TEMATY_OGOLNE = {
    "droga": ["Roadworks in Poland", "Road construction in Poland"],
    "woda": ["Water supply in Poland", "Sewage in Poland"],
    "pociag": ["Koleje Mazowieckie", "Warszawska Kolej Dojazdowa"],
    "bezpieczenstwo": ["Police vehicles in Poland", "Fire engines in Poland", "Fire brigades in Poland", "Police in Poland"],
    "zdrowie": ["Hospitals in Poland", "Ambulances in Poland"],
    "szkola": ["Schools in Poland", "Primary schools in Poland"],
    "sport": ["Football pitches in Poland", "Sports halls in Poland", "Swimming pools in Poland", "Stadiums in Poland", "Orlik"],
    "kultura": ["Libraries in Poland", "Concerts in Poland", "Cultural centres in Poland"],
    "srodowisko": ["Parks in Poland", "Waste containers in Poland"],
    "inwestycje": ["Construction sites in Poland", "Cranes in Poland"],
    "urzad": ["Town halls in Poland", "Municipal offices in Poland"],
    "ogolne": ["Landscapes of Masovian Voivodeship", "Villages in Masovian Voivodeship"],
}
WZORZEC_POLSKI = r"poland|polsk|polish|mazovi|mazowie|warsza|koleje mazowieckie|orlik"
MAX_NA_TEMAT = 60        # tyle plików na temat bierzemy do przejrzenia
GLEBOKOSC_TEMATOW = 4    # kategorie tematyczne bywają głębsze (np. "... by voivodeship"), więc schodzimy niżej niż przy miejscach
# Wyszukiwanie plików po frazach (jak "szukaj" na Commons), także tych, które nie leżą w kategoriach miejsc.
FRAZY_SZUKANIA = ["Grodzisk Mazowiecki", "Grodzisk Mazowiecki park", "Grodzisk Mazowiecki rynek", "Grodzisk Mazowiecki ulica",
                  "Grodzisk Mazowiecki szkoła", "Grodzisk Mazowiecki stadion", "Grodzisk Mazowiecki kościół",
                  "Grodzisk Mazowiecki urząd", "Grodzisk Mazowiecki biblioteka", "Grodzisk Mazowiecki basen"]
MAX_WYNIKOW_FRAZY = 100
MAX_SZUKANYCH = 600
GLEBOKOSC = 2            # tyle poziomów podkategorii schodzimy w dół
MAX_KATEGORII = 80
MAX_PLIKOW = 800
MIN_SZEROKOSC = 1000     # mniejsze zdjęcia nie nadają się na kartę czołówki
PRZERWA = 0.3            # sekundy między zapytaniami do API
MIME_OK = {"image/jpeg", "image/png"}


def pobierz(params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for proba in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                dane = json.loads(r.read().decode("utf-8"))
            time.sleep(PRZERWA)
            return dane
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if proba == 2:
                print(f"  błąd zapytania do Commons: {type(e).__name__}: {e}")
                return {}
            time.sleep(2 * (proba + 1))
    return {}


def czysty_tekst(fragment):
    """Z pola extmetadata (często HTML z linkami) robi zwykły tekst."""
    t = re.sub(r"<[^>]+>", " ", fragment or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def licencja_ok(krotka):
    """Wolne licencje, które pozwalają użyć zdjęcia na stronie z podpisem: CC0, domena publiczna, CC BY, CC BY-SA."""
    l = (krotka or "").lower().strip()
    if not l or re.search(r"\b(nc|nd)\b|non.?commercial|no.?deriv|fair use|all rights|gfdl$|unknown", l):
        return False
    return bool(re.match(r"(cc0|public domain|pd\b|pdm|cc[ -]by)", l))


def uwagi(meta):
    """Ostrzeżenia do ręcznej oceny: ograniczenia z metadanych pliku i słowa sugerujące ludzi lub znaki towarowe."""
    out = []
    ogr = czysty_tekst((meta.get("Restrictions") or {}).get("value"))
    if ogr:
        out.append(f"ograniczenia: {ogr}")
    opis = czysty_tekst((meta.get("ImageDescription") or {}).get("value")).lower()
    if re.search(r"\b(portrait|portret|dzieci|children|uczniowie|crowd|tłum|grupa)\b", opis):
        out.append("prawdopodobnie ludzie: sprawdź wizerunek")
    return out


def rekord(strona):
    """Z odpowiedzi API dla jednego pliku robi rekord kandydata albo None, gdy plik odpada."""
    info = (strona.get("imageinfo") or [None])[0]
    if not info or info.get("mime") not in MIME_OK or (info.get("width") or 0) < MIN_SZEROKOSC:
        return None
    meta = info.get("extmetadata") or {}
    licencja = czysty_tekst((meta.get("LicenseShortName") or {}).get("value"))
    if not licencja_ok(licencja):
        return None
    tytul = strona["title"]
    return {
        "tytul": tytul,
        "strona": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(tytul.replace(" ", "_")),
        "url": info.get("url"),
        "miniatura": info.get("thumburl") or info.get("url"),
        "szerokosc": info.get("width"), "wysokosc": info.get("height"),
        "autor": czysty_tekst((meta.get("Artist") or {}).get("value")) or "autor nieznany",
        "licencja": licencja,
        "licencja_url": czysty_tekst((meta.get("LicenseUrl") or {}).get("value")),
        "opis": czysty_tekst((meta.get("ImageDescription") or {}).get("value"))[:300],
        "data": czysty_tekst((meta.get("DateTimeOriginal") or {}).get("value")),
        "uwagi": uwagi(meta),
        "kategorie": [c for c in czysty_tekst((meta.get("Categories") or {}).get("value")).split("|") if c.strip()],
    }


def znajdz_kategorie(fetch):
    """Kategorie Commons, których nazwa pasuje do miejscowości z listy."""
    wynik = []
    for fraza, wzorzec in MIEJSCA:
        d = fetch({"action": "query", "list": "search", "srsearch": fraza, "srnamespace": "14", "srlimit": "10"})
        for w in (d.get("query") or {}).get("search", []):
            if re.search(wzorzec, w["title"].lower()) and w["title"] not in wynik:
                wynik.append(w["title"])
    return wynik


def znajdz_kategorie_tematow(fetch):
    """temat -> kategorie Commons o Polsce pasujące do fraz z TEMATY_OGOLNE."""
    wynik = {}
    for temat, frazy in TEMATY_OGOLNE.items():
        kat = []
        for fraza in frazy:
            d = fetch({"action": "query", "list": "search", "srsearch": fraza, "srnamespace": "14", "srlimit": "6"})
            for w in (d.get("query") or {}).get("search", []):
                if re.search(WZORZEC_POLSKI, w["title"].lower()) and w["title"] not in kat:
                    kat.append(w["title"])
        wynik[temat] = kat[:4]
    return wynik


def szukaj_plikow(fetch, wykluczone=(), frazy=None):
    """Tytuły plików znalezione wyszukiwarką Commons dla FRAZY_SZUKANIA: [(tytuł, fraza)], bez wykluczonych i powtórzeń."""
    wynik, widziane = [], set(wykluczone)
    for fraza in (frazy or FRAZY_SZUKANIA):
        d = fetch({"action": "query", "list": "search", "srsearch": f"{fraza} filetype:bitmap", "srnamespace": "6",
                   "srlimit": str(MAX_WYNIKOW_FRAZY)})
        for w in (d.get("query") or {}).get("search", []):
            if w["title"] not in widziane and len(wynik) < MAX_SZUKANYCH:
                widziane.add(w["title"])
                wynik.append((w["title"], fraza))
    print(f"  plików znalezionych wyszukiwarką (bez już wybranych): {len(wynik)}")
    return wynik


def zbierz_pliki(fetch, kategorie, limit=None, max_kategorii=None, glebokosc=GLEBOKOSC):
    """Tytuły plików z kategorii i ich podkategorii (do GLEBOKOSC poziomów, z limitami)."""
    limit, max_kategorii = limit or MAX_PLIKOW, max_kategorii or MAX_KATEGORII
    pliki, odwiedzone, kolejka = [], set(), [(k, 0) for k in kategorie]
    while kolejka and len(odwiedzone) < max_kategorii and len(pliki) < limit:
        kat, poziom = kolejka.pop(0)
        if kat in odwiedzone:
            continue
        odwiedzone.add(kat)
        cont = None
        while True:
            par = {"action": "query", "list": "categorymembers", "cmtitle": kat, "cmtype": "file|subcat", "cmlimit": "500"}
            if cont:
                par["cmcontinue"] = cont
            d = fetch(par)
            for m in (d.get("query") or {}).get("categorymembers", []):
                if m["title"].startswith("File:") and m["title"] not in pliki:
                    pliki.append(m["title"])
                elif m["title"].startswith("Category:") and poziom < glebokosc:
                    kolejka.append((m["title"], poziom + 1))
            cont = (d.get("continue") or {}).get("cmcontinue")
            if not cont or len(pliki) >= limit:
                break
    print(f"  kategorii przejrzanych: {len(odwiedzone)}, plików znalezionych: {len(pliki)}")
    return pliki[:limit]


def szczegoly(fetch, tytuly):
    kandydaci, odrzucone = [], 0
    for i in range(0, len(tytuly), 40):
        paczka = tytuly[i:i + 40]
        d = fetch({"action": "query", "prop": "imageinfo", "titles": "|".join(paczka), "iiprop": "url|size|mime|extmetadata",
                   "iiurlwidth": "640"})
        for s in (d.get("query") or {}).get("pages", []):
            r = rekord(s)
            if r:
                kandydaci.append(r)
            else:
                odrzucone += 1
    print(f"  kandydatów: {len(kandydaci)}, odrzuconych (licencja, rozmiar lub format): {odrzucone}")
    return kandydaci


def _karta(k):
    ostrz = "".join(f'<p class="u">{html.escape(u)}</p>' for u in k["uwagi"])
    wartosc = k["tytul"] + (f' | {k["temat_szukany"]}' if k.get("temat_szukany") else "")
    return (
        f'<label class="k"><input type="checkbox" value="{html.escape(wartosc)}">'
        f'<img src="{html.escape(k["miniatura"])}" loading="lazy" alt="" referrerpolicy="no-referrer">'
        f'<b>{html.escape(k["tytul"].removeprefix("File:"))}</b>'
        f'<span>{html.escape(k["autor"][:80])} · {html.escape(k["licencja"])} · {k["szerokosc"]}×{k["wysokosc"]}</span>'
        f'<span>{html.escape(k["opis"][:140])}</span>{ostrz}'
        f'<a href="{html.escape(k["strona"])}" target="_blank" rel="noopener">strona na Commons</a></label>')


def arkusz(kandydaci):
    """Strona HTML do przeglądu: najpierw zdjęcia miejsc, potem ogólne zdjęcia tematyczne (każdy temat osobno).
    Pole wyboru niesie tytuł pliku, a przy zdjęciach tematycznych także temat ("File:X.jpg | droga")."""
    grupy = {"miejsca": []}
    for t in TEMATY_OGOLNE:
        grupy[t] = []
    for k in kandydaci:
        grupy.setdefault(k.get("temat_szukany") or ("szukaj: " + k["grupa"] if k.get("grupa") else "miejsca"), []).append(k)
    sekcje = []
    for nazwa, lista in grupy.items():
        if lista:
            tytul = ("Zdjęcia miejsc w gminie i okolicy" if nazwa == "miejsca" else
                     f"Wyniki wyszukiwania: {nazwa.removeprefix("szukaj: ")}" if nazwa.startswith("szukaj: ") else f"Zdjęcia ogólne, temat: {nazwa}")
            sekcje.append(f'<h2>{html.escape(tytul)} ({len(lista)})</h2><div class="siatka">{"".join(_karta(k) for k in lista)}</div>')
    return (
        '<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="robots" content="noindex">'
        '<title>Kandydaci na zdjęcia</title><style>'
        'body{font-family:system-ui,sans-serif;margin:1rem;max-width:1400px}.siatka{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:1rem}'
        'h2{margin:1.5rem 0 .5rem}.k{display:flex;flex-direction:column;gap:.3rem;border:1px solid #ccc;padding:.6rem;font-size:.85rem}'
        '.k:has(input:checked){outline:3px solid #2563eb}.k img{width:100%;aspect-ratio:16/10;object-fit:cover;background:#eee}'
        '.k span{color:#555}.u{color:#b45309;margin:0}#panel{position:sticky;top:0;background:#fff;padding:.6rem 0;border-bottom:1px solid #ccc;margin-bottom:1rem}'
        '</style></head><body><div id="panel"><b id="n">0</b> zaznaczonych z ' + str(len(kandydaci)) +
        ' <button id="kop">Kopiuj listę zaznaczonych</button> '
        '<span>Zaznacz zdjęcia, których chcesz użyć (kilka na temat), kliknij przycisk i wklej listę do rozmowy.</span></div>'
        + "".join(sekcje) + '<script>'
        'var c=document.querySelectorAll("input"),n=document.getElementById("n");'
        'function z(){var l=[];c.forEach(function(i){if(i.checked)l.push(i.value)});n.textContent=l.length;return l}'
        'c.forEach(function(i){i.addEventListener("change",z)});'
        'document.getElementById("kop").addEventListener("click",function(){var t=z().join("\\n");'
        'navigator.clipboard.writeText(t).then(function(){alert("Skopiowano "+z().length+" tytułów")},function(){prompt("Skopiuj:",t)})});'
        '</script></body></html>')


# ---------- automatyczny wybór zdjęć dla miejscowości gminy ----------
TARGET_NA_WIES = 3          # tyle zdjęć chcemy mieć na miejscowość (liczymy też te już wybrane ręcznie)
WYNIKOW_NA_WIES = 25
# zdjęcia, których nie wybieramy automatycznie: ludzie, cmentarze i groby, imprezy, mecze
NIEPOTRZEBNE = re.compile(r"cmentarz|cmentarn|\bgrob|\bgrób|kirkut|jewish|nagrob|pogrzeb|funeral|portret|portrait|zawodnik|\bmecz|match|"
                          r"dzieci|children|uczni|festyn|konkurs|uroczysto|wizyta|spotkanie|koncert|\blud(zie|zi)", re.I)


def wybierz_dla_wsi(kandydaci, wies, ile):
    """Najlepsze zdjęcia miejscowości bez ludzi: poziome, duże, z nazwą wsi w tytule lub kategoriach."""
    wies_n = re.sub(r"[^a-z0-9]+", " ", wies.lower().translate(str.maketrans("ąćęłńóśźż", "acelnoszz"))).strip()
    dobre = [k for k in kandydaci if not k["uwagi"] and not NIEPOTRZEBNE.search(f'{k["tytul"]} {k["opis"]}')]

    def klucz(k):
        tekst = re.sub(r"[^a-z0-9]+", " ", f'{k["tytul"]} {" ".join(k.get("kategorie", []))}'.lower().translate(
            str.maketrans("ąćęłńóśźż", "acelnoszz")))
        poziome = 1.2 <= (k["szerokosc"] or 1) / (k["wysokosc"] or 1) <= 2.4
        return (poziome, wies_n in tekst, k["szerokosc"] or 0)

    return sorted(dobre, key=klucz, reverse=True)[:ile]


TARGET_NA_TEMAT = 8        # tyle zdjęć ogólnych chcemy mieć na temat (liczymy też wybrane ręcznie)
MAX_Z_AUTORA = 2           # nie więcej zdjęć jednego autora na temat (żeby nie wyszła seria z jednego spaceru)
# budynki z napisami (biblioteka, muzeum, teatr) wprowadzają w błąd przy wpisach o innych miejscach; urząd jest wyjątkiem, bo to nasz ratusz
SZYLDY = re.compile(r"bibliotek|library|muzeum|museum|teatr|theatre|theater|ratusz|town hall", re.I)


def wybierz_dla_tematu(kandydaci, temat, ile):
    """Najlepsze zdjęcia ogólne do tematu: bez ludzi, bez budynków z napisami, poziome, duże i od różnych autorów."""
    def ok(k):
        tekst = f'{k["tytul"]} {k["opis"]}'
        return not k["uwagi"] and not NIEPOTRZEBNE.search(tekst) and (temat == "urzad" or not SZYLDY.search(tekst))
    def klucz(k):
        return (1.2 <= (k["szerokosc"] or 1) / (k["wysokosc"] or 1) <= 2.4, k["szerokosc"] or 0)
    wybrane, autorzy = [], {}
    for k in sorted(filter(ok, kandydaci), key=klucz, reverse=True):
        if autorzy.get(k["autor"], 0) >= MAX_Z_AUTORA:
            continue
        autorzy[k["autor"]] = autorzy.get(k["autor"], 0) + 1
        wybrane.append(k)
        if len(wybrane) >= ile:
            break
    return wybrane


def main_tematy_auto(fetch=pobierz, katalog=ROOT / "data"):
    """Uzupełnia zdjęcia ogólne do każdego tematu automatycznie do TARGET_NA_TEMAT. Zapisuje data/zdjecia_tematy.txt (gotowe do pobrania)
    i podgląd data/zdjecia_tematy.html. Zdjęcia wybrane ręcznie w zdjecia_wybor.txt liczą się do celu i mają pierwszeństwo."""
    import zdjecia_pobierz as zp
    wybrane = zp.wczytaj_wybor(katalog / "zdjecia_wybor.txt")
    juz = {w[0] for w in wybrane}
    mamy = {}
    for t, temat, slowa, mj, zrodla in wybrane:
        if temat and not slowa and not zrodla and not mj:
            mamy[temat] = mamy.get(temat, 0) + 1
    kategorie = znajdz_kategorie_tematow(fetch)
    linie, podglad = [], []
    for temat, kat in kategorie.items():
        brak = TARGET_NA_TEMAT - mamy.get(temat, 0)
        if brak <= 0 or not kat:
            continue
        kand = [k for k in szczegoly(fetch, [t for t in zbierz_pliki(fetch, kat, MAX_NA_TEMAT, 30, GLEBOKOSC_TEMATOW) if t not in juz])]
        wybor = wybierz_dla_tematu(kand, temat, brak)
        print(f"  {temat}: kandydatów {len(kand)}, wybrano {len(wybor)}")
        for k in wybor:
            juz.add(k["tytul"])
            linie.append(f'{k["tytul"]} | {temat}')
            podglad.append({**k, "temat_szukany": temat})
    katalog.mkdir(exist_ok=True)
    (katalog / "zdjecia_tematy.txt").write_text("\n".join(linie) + ("\n" if linie else ""), encoding="utf-8")
    (katalog / "zdjecia_tematy.html").write_text(arkusz(podglad), encoding="utf-8")
    print(f"Wybrano automatycznie {len(linie)} zdjęć ogólnych: data/zdjecia_tematy.txt")
    return 0


def main_wsie(fetch=pobierz, katalog=ROOT / "data"):
    """Dla każdej miejscowości gminy szuka zdjęć na Commons (nazwa wsi i Grodzisk Mazowiecki w tekście pliku) i wybiera automatycznie
    brakujące do TARGET_NA_WIES. Zapisuje data/zdjecia_wsie.txt (gotowe do pobrania) oraz arkusz podglądowy data/zdjecia_wsie.html."""
    import zdjecia_pobierz as zp
    from klasyfikacja import PLACES, w_gminie
    wsie = [n for n in PLACES if w_gminie(n)]
    wybrane = zp.wczytaj_wybor(katalog / "zdjecia_wybor.txt")
    juz = {w[0] for w in wybrane}
    mamy = {}
    for t, temat, slowa, mj, zrodla in wybrane:
        m = mj or ("" if temat and not slowa and not zrodla else zp.miejsce(t))
        mamy[m] = mamy.get(m, 0) + 1
    linie, podglad = [], []
    for wies in wsie:
        brak = TARGET_NA_WIES - mamy.get(wies, 0)
        if brak <= 0:
            continue
        d = fetch({"action": "query", "list": "search", "srsearch": f'"{wies}" "Grodzisk Mazowiecki" filetype:bitmap',
                   "srnamespace": "6", "srlimit": str(WYNIKOW_NA_WIES)})
        tytuly = [w["title"] for w in (d.get("query") or {}).get("search", []) if w["title"] not in juz]
        wybor = wybierz_dla_wsi(szczegoly(fetch, tytuly), wies, brak) if tytuly else []
        print(f"  {wies}: znaleziono {len(tytuly)}, wybrano {len(wybor)}")
        for k in wybor:
            juz.add(k["tytul"])
            linie.append(f'{k["tytul"]} | | | {wies}')
            podglad.append({**k, "grupa": wies})
    katalog.mkdir(exist_ok=True)
    (katalog / "zdjecia_wsie.txt").write_text("\n".join(linie) + ("\n" if linie else ""), encoding="utf-8")
    (katalog / "zdjecia_wsie.html").write_text(arkusz(podglad), encoding="utf-8")
    print(f"Wybrano automatycznie {len(linie)} zdjęć dla {len({p['grupa'] for p in podglad})} miejscowości: data/zdjecia_wsie.txt")
    return 0


def _wybrane_tytuly(katalog):
    sciezka = katalog / "zdjecia_wybor.txt"
    if not sciezka.exists():
        return set()
    return {l.split("|")[0].strip().replace("_", " ") for l in sciezka.read_text(encoding="utf-8").splitlines() if l.strip().startswith("File:")}


def main_szukaj(fetch=pobierz, katalog=ROOT / "data", frazy=None):
    """Kandydaci z wyszukiwarki Commons po frazach o Grodzisku. Pomija pliki już wybrane w data/zdjecia_wybor.txt."""
    print("Szukam plików na Commons po frazach...")
    znalezione = szukaj_plikow(fetch, _wybrane_tytuly(katalog), frazy)
    if not znalezione:
        print("Wyszukiwarka nic nie zwróciła. Sprawdź połączenie z Commons.")
        return 1
    fraza_pliku = dict(znalezione)
    kandydaci = [{**k, "grupa": fraza_pliku[k["tytul"]]} for k in szczegoly(fetch, [t for t, _ in znalezione])]
    kandydaci.sort(key=lambda k: (-(k["szerokosc"] or 0)))
    katalog.mkdir(exist_ok=True)
    (katalog / "zdjecia_kandydaci.json").write_text(json.dumps(kandydaci, ensure_ascii=False, indent=1), encoding="utf-8")
    (katalog / "zdjecia_kandydaci.html").write_text(arkusz(kandydaci), encoding="utf-8")
    print(f"Zapisano {len(kandydaci)} kandydatów: data/zdjecia_kandydaci.html (arkusz) i .json")
    return 0


def main(fetch=pobierz, katalog=ROOT / "data", miejsca=True):
    """miejsca=False: tylko zdjęcia ogólne do tematów (bez ponownego przeglądania zdjęć miejsc)."""
    print("Szukam kategorii Commons dla gminy i powiatu..." if miejsca else "Szukam kategorii tematycznych Commons...")
    kategorie = znajdz_kategorie(fetch) if miejsca else []
    print(f"  kategorie miejsc: {len(kategorie)}: {', '.join(k.removeprefix('Category:') for k in kategorie)}")
    tematy = znajdz_kategorie_tematow(fetch)
    print("  kategorie tematyczne: " + "; ".join(f"{t}: {len(k)}" for t, k in tematy.items()))
    if not kategorie and not any(tematy.values()):
        print("Nie znaleziono żadnej kategorii. Sprawdź połączenie z Commons.")
        return 1
    kandydaci = szczegoly(fetch, zbierz_pliki(fetch, kategorie)) if kategorie else []
    widziane = {k["tytul"] for k in kandydaci}
    for temat, kat in tematy.items():
        if not kat:
            continue
        for k in szczegoly(fetch, zbierz_pliki(fetch, kat, MAX_NA_TEMAT, 30, GLEBOKOSC_TEMATOW)):
            if k["tytul"] not in widziane:
                widziane.add(k["tytul"])
                kandydaci.append({**k, "temat_szukany": temat})
    kandydaci.sort(key=lambda k: (-(k["szerokosc"] or 0)))
    katalog.mkdir(exist_ok=True)
    (katalog / "zdjecia_kandydaci.json").write_text(json.dumps(kandydaci, ensure_ascii=False, indent=1), encoding="utf-8")
    (katalog / "zdjecia_kandydaci.html").write_text(arkusz(kandydaci), encoding="utf-8")
    print(f"Zapisano {len(kandydaci)} kandydatów: data/zdjecia_kandydaci.html (arkusz) i .json")
    return 0


if __name__ == "__main__":
    if "--tematy-auto" in sys.argv:
        sys.exit(main_tematy_auto())
    if "--wsie" in sys.argv:
        sys.exit(main_wsie())
    if "--szukaj" in sys.argv:
        # własne frazy z zmiennej FRAZA, oddzielone średnikami (np. "Książenice; Książenice szkoła"); bez niej domyślny zestaw o Grodzisku
        sys.exit(main_szukaj(frazy=[f.strip() for f in os.environ.get("FRAZA", "").split(";") if f.strip()] or None))
    sys.exit(main(miejsca="--tematy" not in sys.argv))

# wersja-kompletu: 2026-10-25-6
