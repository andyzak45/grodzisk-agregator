"""Własne grafiki poglądowe przy wpisach (SVG, bez zewnętrznych plików i bez praw osób trzecich).

Temat grafiki dobieramy ze słów w tytule i notce, a gdy nic nie pasuje, z rodzaju wpisu. Wszystkie grafiki leżą
w jednym "sprite" na początku strony, a karty tylko się do nich odwołują, więc strona rośnie o ok. 6 KB, a nie o ok. 6 KB na kartę.
Kolory pochodzą z klasy rodzaju (.k-inw itd.): ciemny to currentColor, a "wycięcia" mają kolor tła (var(--t)).
"""
import html
import json
import re
import zlib
from collections import Counter
from pathlib import Path

from klasyfikacja import norm

OPISY = {
    "ogolne": "Grodzisk Mazowiecki", "droga": "drogi i ruch", "woda": "woda i kanalizacja", "pociag": "pociągi i komunikacja",
    "bezpieczenstwo": "bezpieczeństwo", "zdrowie": "zdrowie", "szkola": "szkoła i edukacja", "sport": "sport",
    "kultura": "kultura i wydarzenia", "srodowisko": "środowisko i odpady", "inwestycje": "inwestycje", "urzad": "urząd i rada",
}

# kolejność ma znaczenie: pierwszy pasujący temat wygrywa; wzorce dopasowujemy od początku słowa (po norm)
TEMATY = [
    ("pociag", r"\b(pociag|wkd|kolej(?:i|ow\w*)?\b|dworc|rozklad jazdy|autobus|peron)"),   # "kolejność" i "kolejka" to nie kolej
    ("woda", r"\b(woda|wody|wodoc|kanaliz|scie[kg]|deszczow|wodn)"),
    ("bezpieczenstwo", r"\b(policj|strazy?\b|pozar|wypad|kradziez|oszust|zagin|ostrze|alarm|bezpiecz|interwenc)"),
    ("zdrowie", r"\b(zdrow|szpital|badani|mammograf|lekarz|profilakt|szczepi|przychodni|onkolog)"),
    ("szkola", r"\b(szkol|przedszkol|uczn|nauczyc|edukac|stypend|lekcj)"),
    ("sport", r"\b(mecz|sport|pilk|siatk|turniej|bieg\b|basen|trening|liga|stadion|szach)"),
    ("droga", r"\b(drog|ulic|remont|objazd|chodnik|rondo|zamkni|parking|przejsc|jezdni)|w ruchu|ruch(u)? (drogow|jednokier)"),
    ("kultura", r"\b(koncert|kultur|bibliote[kc]|wystaw|spektakl|kino|film|muzy|teatr|festiwal|mediate|warsztat|jarmark|przedstawieni|seans|opery|opera|operze|pokaz\b|swietlic)"),
    ("inwestycje", r"\b(inwestyc|budow|przetarg|dofinansow|modernizac|rewitalizac|pozwolen)"),
    ("srodowisko", r"\b(odpad|smiec|park|drzew|zieleni|las|ekolog|recykl|lisci|klimat|zbiork|tekstyli)"),
    ("urzad", r"\b(urzad|rad[aniy]\b|sesj|uchwal|burmistrz|konsultac|wybor|budzet|bip\b|wniosk|nabor)"),
]
PO_RODZAJU = {"ost": "bezpieczenstwo", "zdr": "bezpieczenstwo", "wyd": "kultura", "inw": "inwestycje", "spo": "sport", "inne": "ogolne"}

_G = '<path d="M0 118h320v22H0z" opacity=".3"/>'
_SYMBOLE = {
    "ogolne": _G + '<path d="M20 118V84l20-16 20 16v34z" opacity=".55"/><path d="M80 118V70h26v48z"/><path d="M80 70l13-24 13 24z"/>'
              '<path d="M120 118V90h40v28z" opacity=".55"/><path d="M114 90l26-20 26 20z" opacity=".85"/>'
              '<circle cx="204" cy="94" r="20" opacity=".45"/><path d="M202 118h4V96h-4z"/>'
              '<path d="M236 118V80h30v38z" opacity=".55"/><path d="M276 118V92h30v26z" opacity=".85"/><circle cx="282" cy="30" r="14" opacity=".3"/>',
    "droga": _G + '<path d="M0 72q60-26 120 0v14H0z" opacity=".3"/><path d="M100 118L150 42h20l50 76z" opacity=".75"/>'
             '<path d="M158 112h4v-10h-4zM158 92h4v-8h-4zM159 74h2v-6h-2zM159.5 60h1v-4h-1z" fill="var(--t)"/>'
             '<path d="M246 118l10-36 10 36z"/><rect x="240" y="116" width="32" height="6" rx="2"/><path d="M250 100h12l-2 8h-8z" fill="var(--t)"/>',
    "woda": '<path d="M160 18c24 34 38 50 38 70a38 38 0 01-76 0c0-20 14-36 38-70z"/>'
            '<path d="M144 88a16 16 0 0016 16" fill="none" stroke="var(--t)" stroke-width="5" stroke-linecap="round"/>'
            '<rect x="20" y="44" width="76" height="12" rx="6" opacity=".45"/><rect x="226" y="34" width="76" height="12" rx="6" opacity=".45"/>'
            '<path d="M0 118q20-12 40 0t40 0 40 0 40 0 40 0 40 0 40 0 40 0v22H0z" opacity=".4"/>'
            '<path d="M0 129q20-10 40 0t40 0 40 0 40 0 40 0 40 0 40 0 40 0v11H0z" opacity=".75"/>',
    "pociag": _G + '<path d="M0 126h320M0 134h320" stroke="currentColor" stroke-width="3" opacity=".5"/>'
              '<rect x="50" y="40" width="220" height="68" rx="16"/><rect x="68" y="54" width="42" height="26" rx="4" fill="var(--t)"/>'
              '<rect x="122" y="54" width="42" height="26" rx="4" fill="var(--t)"/><rect x="176" y="54" width="42" height="26" rx="4" fill="var(--t)"/>'
              '<rect x="228" y="54" width="28" height="44" rx="4" fill="var(--t)"/><rect x="50" y="88" width="170" height="6" fill="var(--t)" opacity=".5"/>'
              '<circle cx="96" cy="112" r="9"/><circle cx="224" cy="112" r="9"/><path d="M150 40l12-16 12 16" fill="none" stroke="currentColor" stroke-width="4"/>',
    "bezpieczenstwo": '<path d="M160 16l58 20v42c0 30-24 50-58 62-34-12-58-32-58-62V36z"/>'
                      '<path d="M160 40v76c20-8 34-22 34-40V50z" fill="var(--t)" opacity=".35"/>'
                      '<path d="M136 72l18 18 30-36" fill="none" stroke="var(--t)" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>'
                      '<path d="M28 40l26 10M24 72h28M28 104l26-10M292 40l-26 10M296 72h-28M292 104l-26-10" stroke="currentColor" stroke-width="5" stroke-linecap="round" opacity=".4"/>',
    "zdrowie": '<path d="M0 104h98l10-26 14 46 12-32 10 12h176" fill="none" stroke="currentColor" stroke-width="4" opacity=".4"/>'
               '<path d="M146 22h28v34h34v28h-34v34h-28V84h-34V56h34z"/>',
    "szkola": _G + '<path d="M80 118V64h160v54z" opacity=".6"/><path d="M68 64l92-38 92 38z"/><rect x="148" y="86" width="24" height="32" fill="var(--t)"/>'
              '<rect x="96" y="78" width="22" height="18" fill="var(--t)"/><rect x="202" y="78" width="22" height="18" fill="var(--t)"/>'
              '<path d="M160 26V6" stroke="currentColor" stroke-width="3"/><path d="M160 6h26l-7 8 7 8h-26z"/>',
    "sport": '<path d="M0 118h320v22H0z" opacity=".4"/><path d="M30 118V58h56v60M290 118V58h-56v60" fill="none" stroke="currentColor" stroke-width="5" opacity=".55"/>'
             '<circle cx="160" cy="66" r="42"/><path d="M160 42l18 13-7 21h-22l-7-21z" fill="var(--t)"/>'
             '<path d="M160 42V24M178 55l19-6M171 76l12 17M149 76l-12 17M142 55l-19-6" stroke="var(--t)" stroke-width="4" stroke-linecap="round"/>'
             '<ellipse cx="160" cy="124" rx="40" ry="6" opacity=".35"/>',
    "kultura": '<rect x="56" y="18" width="208" height="100" rx="4" opacity=".25"/><path d="M56 18h208v16H56z"/>'
               '<path d="M56 34c22 0 34 30 34 84H56zM264 34c-22 0-34 30-34 84h34z" opacity=".85"/>'
               '<circle cx="146" cy="98" r="10"/><circle cx="182" cy="92" r="10"/><path d="M156 98V54l36-8v46" fill="none" stroke="currentColor" stroke-width="5"/>'
               '<path d="M0 118h320v22H0z" opacity=".35"/>',
    "srodowisko": _G + '<circle cx="72" cy="76" r="30" opacity=".55"/><rect x="68" y="96" width="8" height="22"/>'
                  '<circle cx="152" cy="62" r="40"/><rect x="147" y="94" width="10" height="24"/>'
                  '<path d="M152 38c20 10 24 28 0 44-24-16-20-34 0-44z" fill="var(--t)" opacity=".4"/>'
                  '<circle cx="240" cy="84" r="26" opacity=".55"/><rect x="236" y="98" width="8" height="20"/><circle cx="278" cy="26" r="12" opacity=".3"/>',
    "inwestycje": _G + '<path d="M200 118V50h62v68z" opacity=".6"/><path d="M210 62h10v10h-10zM232 62h10v10h-10zM210 84h10v10h-10zM232 84h10v10h-10z" fill="var(--t)"/>'
                  '<path d="M76 118V22h8v96z"/><path d="M34 26h176v8H34z"/><path d="M80 22L36 34M80 22l64 12" stroke="currentColor" stroke-width="3" fill="none"/>'
                  '<rect x="34" y="34" width="16" height="16"/><path d="M178 34v38" stroke="currentColor" stroke-width="3"/><rect x="168" y="72" width="20" height="14" rx="2"/>',
    "urzad": _G + '<path d="M66 54L160 16l94 38z"/><rect x="74" y="58" width="172" height="8"/>'
             '<path d="M90 70h14v40H90zM122 70h14v40h-14zM154 70h14v40h-14zM186 70h14v40h-14zM218 70h14v40h-14z"/><rect x="74" y="110" width="172" height="8"/>'
             '<circle cx="160" cy="40" r="8" fill="var(--t)"/>',
}


# ---------- zdjęcia z Wikimedia Commons (data/zdjecia.json, pliki w zdjecia/) ----------
MIASTO = "Grodzisk Mazowiecki"
# Dla wpisu o mieście lub całej gminie zdjęcie dobieramy tylko, gdy TYTUŁ wyraźnie mówi o kolei lub urzędzie. Wzorce są ostre
# celowo: lepiej grafika niż zdjęcie WKD przy wiadomości o bibliotece, w której jest "kolejność zgłoszeń".
TEMATY_ZDJEC_MIASTA = [
    ("pociag", r"\b(wkd|pociag\w*|peron\w*|koleje mazowieckie|linia kolejowa|kolej(?:i|ow\w*)?\b|stacj\w* (?:kolej|wkd))"),
    ("urzad", r"\b(urzad\w* (?:miejsk|miasta|gminy)|burmistrz\w*|rad\w* miejsk\w*|sesj\w* rady|starostw\w*|starost\w*)"),
]
ZDJECIA = []
_UZYCIA = Counter()
_WYBOR = {}


def dozwolone_tytuly(katalog_data):
    """Tytuły plików z data/zdjecia_wybor.txt i data/zdjecia_wsie.txt albo None, gdy żadnego z tych plików nie ma (wtedy bez filtra)."""
    wynik, jest = set(), False
    for nazwa in ("zdjecia_wybor.txt", "zdjecia_wsie.txt"):
        sciezka = Path(katalog_data) / nazwa
        if sciezka.exists():
            jest = True
            for linia in sciezka.read_text(encoding="utf-8").splitlines():
                t = linia.split("|")[0].strip().replace("_", " ")
                if t.startswith("File:"):
                    wynik.add(t)
    return wynik if jest else None


def wczytaj_zdjecia(sciezka, korzen, dozwolone=None):
    """Lista zdjęć z data/zdjecia.json, z pominięciem tych, których pliku nie ma na dysku."""
    try:
        dane = json.loads(Path(sciezka).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [z for z in dane if isinstance(z, dict) and z.get("plik") and (Path(korzen) / z["plik"]).exists()
            and (dozwolone is None or z.get("tytul") in dozwolone)]


def ustaw_zdjecia(lista):
    ZDJECIA[:] = lista
    _UZYCIA.clear()
    _WYBOR.clear()


def temat_zdjecia(it):
    """Temat zdjęcia dla wpisu o mieście lub gminie: tylko z tytułu i tylko ostre wzorce, inaczej None (zostaje grafika)."""
    t = norm(f'{it.get("title", "")} {it.get("tytul") or ""}')
    return next((nazwa for nazwa, wzorzec in TEMATY_ZDJEC_MIASTA if re.search(wzorzec, t)), None)


def wybierz_zdjecie(it):
    """Zdjęcie dla wpisu albo None. Wpis o wsi dostaje zdjęcie tej wsi, wpis o mieście lub gminie tylko zdjęcie pasujące
    do tematu (kolej, urząd). Wybór jest stały dla wpisu, a zdjęcia rotują, żeby to samo nie wisiało przy każdym wpisie."""
    klucz = it.get("id") or it["url"]
    if klucz in _WYBOR:
        return _WYBOR[klucz]
    miejsce = it["place"].split("|")[0]
    tytul_n = norm(f'{it.get("title", "")} {it.get("tytul") or ""}')
    nazwy = [z for z in ZDJECIA if z["miejsce"] in (miejsce, "cała gmina")
             and ((z.get("slowa") and re.search(r"\b(?:" + "|".join(z["slowa"]) + ")", tytul_n)) or it.get("source_id") in z.get("zrodla", ()))]
    if nazwy:                      # wpis o konkretnym miejscu (np. Mediateka) dostaje zdjęcie tego miejsca, jeśli je mamy; "slowa" to rdzenie bez końcówek, bo polskie nazwy się odmieniają (Mediateka, Mediatece, Mediatekę)
        kand = nazwy
    elif miejsce in ("cała gmina", "okolica", MIASTO):
        t = temat_zdjecia(it)
        kand = [z for z in ZDJECIA if z["miejsce"] == MIASTO and z["temat"] == t and not z.get("slowa") and not z.get("zrodla")] if t else []
    else:
        kand = [z for z in ZDJECIA if z["miejsce"] == miejsce and not z.get("slowa") and not z.get("zrodla")]
    if not kand and it["kind"] != "zdr":      # zapas: zdjęcie ogólne do tematu (nie przy zdarzeniach policji, by nie sugerować miejsca)
        t = temat_ze_slow(it) or "ogolne"
        kand = ([z for z in ZDJECIA if not z["miejsce"] and z["temat"] == t]
                or ([z for z in ZDJECIA if z["temat"] == t and not z.get("slowa") and not z.get("zrodla")] if t != "ogolne" else [])      # brak zdjęcia ogólnego: dowolne z tego tematu (np. ratusz, stadion)
                or [z for z in ZDJECIA if not z["miejsce"] and z["temat"] == "ogolne"])
    wybrane = min(kand, key=lambda z: (_UZYCIA[z["plik"]], zlib.crc32(f'{klucz}{z["plik"]}'.encode()))) if kand else None
    if wybrane:
        _UZYCIA[wybrane["plik"]] += 1
    _WYBOR[klucz] = wybrane
    return wybrane


def opis_zdjecia(z):
    """Tekst w podpowiedzi po najechaniu na zdjęcie (atrybut title). Pełne uznanie autorstwa jest na stronie zdjecia.html."""
    czesci = [f'Fot.: {z["autor"]}'] if z.get("autor") else []
    if z.get("licencja"):
        czesci.append(z["licencja"])
    return html.escape(", ".join(czesci), quote=True)


def sprite():
    """Ukryty blok <symbol> ze wszystkimi grafikami; wstawiany raz na początku strony."""
    sym = "".join(f'<symbol id="ilu-{k}" viewBox="0 0 320 140">{v}</symbol>' for k, v in _SYMBOLE.items())
    return f'<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>{sym}</defs></svg>'


def temat_ze_slow(it):
    """Temat wynikający ze słów w tytule (najpierw), a gdy tytuł nic nie mówi, w tytule i notce. None, gdy żadne słowo nie pasuje."""
    tytul = f'{it.get("title", "")} {it.get("tytul") or ""}'
    for tekst in (norm(tytul), norm(f'{tytul} {it.get("text") or ""}')):
        for nazwa, wzorzec in TEMATY:
            if re.search(wzorzec, tekst):
                return nazwa
    return None


def temat(it):
    """Temat grafiki: ze słów, a w ostateczności z rodzaju wpisu."""
    return temat_ze_slow(it) or PO_RODZAJU.get(it["kind"], "ogolne")


def ilustracja(it, klasa="ilu"):
    """Karta ze zdjęciem (pole "obraz", np. od źródła, które wyraziło zgodę) albo z naszą grafiką poglądową."""
    obraz = it.get("obraz")
    if obraz and obraz.startswith("https://"):      # zdjęcie ze źródła wpisu
        return (f'<div class="{klasa} foto k-{it["kind"]}"><img src="{html.escape(obraz)}" alt="" title="Fot.: {html.escape(it["source"], quote=True)}" '
                f'loading="lazy" referrerpolicy="no-referrer"></div>')
    z = wybierz_zdjecie(it)
    if z:      # zdjęcie w ramce o stałej proporcji, bez podpisu (autorzy i licencje są na stronie zdjecia.html)
        return (f'<div class="{klasa} foto k-{it["kind"]}"><img src="{html.escape(z["plik"])}" alt="" title="{opis_zdjecia(z)}" '
                f'loading="lazy" decoding="async"></div>')
    t = temat(it)
    return (f'<div class="{klasa} k-{it["kind"]}" role="img" aria-label="Grafika poglądowa: {OPISY[t]}">'
            f'<svg viewBox="0 0 320 140" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><use href="#ilu-{t}"/></svg></div>')


def tlo_czolowki(it):
    """Tło dużej karty: zdjęcie albo grafika. Zwraca (znacznik, dodatkowa klasa)."""
    z = wybierz_zdjecie(it) if not it.get("obraz") else None
    if z:
        return f'<img class="hero-foto" src="{html.escape(z["plik"])}" alt="" title="{opis_zdjecia(z)}" decoding="async">', " z-foto"
    return (f'<svg class="hero-ilu" viewBox="0 0 320 140" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
            f'<use href="#ilu-{temat(it)}"/></svg>'), ""

# wersja-kompletu: 2026-10-25-4
