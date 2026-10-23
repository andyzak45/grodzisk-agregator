"""Zbiera kandydatów na zdjęcia z Wikimedia Commons (wolne licencje) dla gminy i powiatu grodziskiego.

Uruchamiany ręcznie (workflow "Zbieranie zdjęć z Wikimedia Commons"). Niczego nie wstawia na stronę: zapisuje
  data/zdjecia_kandydaci.json  (pełne dane: autor, licencja, adresy)
  data/zdjecia_kandydaci.html  (arkusz przeglądowy z miniaturami; zaznaczasz zdjęcia, które nam pasują)
Zdjęcia wybiera człowiek: skrypt tylko odsiewa to, czego na pewno nie wolno użyć (licencje z NC, ND, brak licencji,
zbyt małe pliki, formaty inne niż JPEG i PNG) i oznacza ostrzeżenia (znaki towarowe, prawa osobiste).
Użycie: python zdjecia_commons.py
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


def zbierz_pliki(fetch, kategorie):
    """Tytuły plików z kategorii i ich podkategorii (do GLEBOKOSC poziomów, z limitami)."""
    pliki, odwiedzone, kolejka = [], set(), [(k, 0) for k in kategorie]
    while kolejka and len(odwiedzone) < MAX_KATEGORII and len(pliki) < MAX_PLIKOW:
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
                elif m["title"].startswith("Category:") and poziom < GLEBOKOSC:
                    kolejka.append((m["title"], poziom + 1))
            cont = (d.get("continue") or {}).get("cmcontinue")
            if not cont or len(pliki) >= MAX_PLIKOW:
                break
    print(f"  kategorii przejrzanych: {len(odwiedzone)}, plików znalezionych: {len(pliki)}")
    return pliki[:MAX_PLIKOW]


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


def arkusz(kandydaci):
    """Strona HTML do przeglądu: miniatury, autor, licencja, pole wyboru i przycisk kopiujący listę wybranych."""
    karty = []
    for k in kandydaci:
        ostrz = "".join(f'<p class="u">{html.escape(u)}</p>' for u in k["uwagi"])
        karty.append(
            f'<label class="k"><input type="checkbox" value="{html.escape(k["tytul"])}">'
            f'<img src="{html.escape(k["miniatura"])}" loading="lazy" alt="" referrerpolicy="no-referrer">'
            f'<b>{html.escape(k["tytul"].removeprefix("File:"))}</b>'
            f'<span>{html.escape(k["autor"][:80])} · {html.escape(k["licencja"])} · {k["szerokosc"]}×{k["wysokosc"]}</span>'
            f'<span>{html.escape(k["opis"][:140])}</span>{ostrz}'
            f'<a href="{html.escape(k["strona"])}" target="_blank" rel="noopener">strona na Commons</a></label>')
    return (
        '<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="robots" content="noindex">'
        '<title>Kandydaci na zdjęcia</title><style>'
        'body{font-family:system-ui,sans-serif;margin:1rem;max-width:1400px}.siatka{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:1rem}'
        '.k{display:flex;flex-direction:column;gap:.3rem;border:1px solid #ccc;padding:.6rem;font-size:.85rem}'
        '.k:has(input:checked){outline:3px solid #2563eb}.k img{width:100%;aspect-ratio:16/10;object-fit:cover;background:#eee}'
        '.k span{color:#555}.u{color:#b45309;margin:0}#panel{position:sticky;top:0;background:#fff;padding:.6rem 0;border-bottom:1px solid #ccc;margin-bottom:1rem}'
        '</style></head><body><div id="panel"><b id="n">0</b> zaznaczonych z ' + str(len(kandydaci)) +
        ' <button id="kop">Kopiuj listę zaznaczonych</button> '
        '<span>Zaznacz zdjęcia, których chcesz użyć, kliknij przycisk i wklej listę do rozmowy.</span></div>'
        '<div class="siatka">' + "".join(karty) + '</div><script>'
        'var c=document.querySelectorAll("input"),n=document.getElementById("n");'
        'function z(){var l=[];c.forEach(function(i){if(i.checked)l.push(i.value)});n.textContent=l.length;return l}'
        'c.forEach(function(i){i.addEventListener("change",z)});'
        'document.getElementById("kop").addEventListener("click",function(){var t=z().join("\\n");'
        'navigator.clipboard.writeText(t).then(function(){alert("Skopiowano "+z().length+" tytułów")},function(){prompt("Skopiuj:",t)})});'
        '</script></body></html>')


def main(fetch=pobierz, katalog=ROOT / "data"):
    print("Szukam kategorii Commons dla gminy i powiatu...")
    kategorie = znajdz_kategorie(fetch)
    print(f"  kategorie: {len(kategorie)}: {', '.join(k.removeprefix('Category:') for k in kategorie)}")
    if not kategorie:
        print("Nie znaleziono żadnej kategorii. Sprawdź połączenie z Commons.")
        return 1
    kandydaci = szczegoly(fetch, zbierz_pliki(fetch, kategorie))
    kandydaci.sort(key=lambda k: (-(k["szerokosc"] or 0)))
    katalog.mkdir(exist_ok=True)
    (katalog / "zdjecia_kandydaci.json").write_text(json.dumps(kandydaci, ensure_ascii=False, indent=1), encoding="utf-8")
    (katalog / "zdjecia_kandydaci.html").write_text(arkusz(kandydaci), encoding="utf-8")
    print(f"Zapisano {len(kandydaci)} kandydatów: data/zdjecia_kandydaci.html (arkusz) i .json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
