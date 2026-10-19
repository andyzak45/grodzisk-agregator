"""Klasyfikacja wpisów: rodzaj informacji, miejscowość i data wydarzenia.

Wszystko oparte na regułach (bez AI), więc wynik jest przewidywalny i da się go testować.
Dopasowanie działa na tekście bez polskich znaków i końcówek (prefiksy słów).
"""
import re
import unicodedata
from datetime import date

CALA_GMINA = "cała gmina"


def norm(text):
    """Małe litery, bez polskich znaków (ł nie rozkłada się w NFD, więc osobno)."""
    t = text.lower().replace("ł", "l")
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# Kolejność ma znaczenie: pierwsza pasująca reguła wygrywa.
KIND_RULES = [
    ("ost", ["ostrzez", "alert", "awari", "brak pradu", "brak wody", "utrudnien", "objazd",
             "wscieklizn", "ewakuac", "zagrozeni", "komunikat kryzysow"]),
    ("zdr", ["policj", "zatrzyman", "oszust", "wypad", "kolizj", "pozar", "kradzie",
             "potracon", "interwencj", "zgon", "smierc", "zginel", "nieletni"]),
    ("spo", ["mecz", "pilk", "siatk", "tenis", "pogon", "sparta", "bogoria", "liga", "ligi",
             "bieg", "turniej", "zawod", "koszyk", "plywa", "kort", "mistrzostw"]),
    ("wyd", ["koncert", "spektakl", "warsztat", "festiwal", "spotkani", "wystaw", "seans",
             "impre", "jarmark", "kiermasz", "targi", "piknik", "wydarzeni", "zapraszam",
             "zajec", "teatr", "noc bibliotek", "rajd", "cosplay", "stand-up"]),
    ("inw", ["przetarg", "inwestycj", "remont", "budow", "przebudow", "modernizacj", "droga",
             "drogi", "drog ", "chodnik", "oswietlen", "wodociag", "kanalizac", "uchwal",
             "budzet", "dofinansowan", "plan ogoln", "planu ogoln", "sesj", "umow", "wniosk", "konsultacj",
             "rekultywac", "parking", "sciezk"]),
]
_KIND_RE = [(k, re.compile(r"\b(?:" + "|".join(map(re.escape, stems)) + ")")) for k, stems in KIND_RULES]


def klasyfikuj_rodzaj(title, hint=None):
    t = norm(title)
    for kind, rx in _KIND_RE:
        if rx.search(t):
            return kind
    return hint or "inne"


# Wzorce dotyczą tekstu znormalizowanego (bez polskich znaków).
PLACES = {
    "Książenice": r"ksiazenic", "Adamowizna": r"adamowizn", "Odrano-Wola": r"odrano",
    "Opypy": r"opyp", "Szczęsne": r"szczesn", "Czarny Las": r"czarn\w+ las",
    "Radonie": r"radoni", "Kałęczyn": r"kaleczyn", "Chrzanów Mały": r"chrzanow\w* mal",
    "Chrzanów Duży": r"chrzanow\w* duz", "Kozery": r"\bkozer(?:y|ach|ow)\b",
    "Kozerki": r"kozerk", "Kozery Nowe": r"kozer\w* now", "Janinów": r"janinow",
    "Natolin": r"natolin", "Chlebnia": r"chlebni", "Kraśnicza Wola": r"krasnicz",
    "Marynin": r"marynin", "Makówka": r"makowk", "Izdebno Kościelne": r"izdebn\w* koscieln",
    "Izdebno Nowe": r"izdebn\w* now", "Izdebno Małe": r"izdebn\w* mal",
    "Wólka Grodziska": r"wolk\w* grodzisk", "Mościska": r"mosciska",
    "Tłuste": r"tlust", "Kady": r"\bkad(?:y|ach)\b", "Władków": r"wladk",
    "Zabłotnia": r"zablotni", "Kłudno Stare": r"kludn\w* star", "Kłudno Nowe": r"kludn\w* now",
    "Kłudzienko": r"kludzienk", "Żuków": r"zukow", "Wężyk": r"wezyk", "Adamów": r"\badamow(?:ie)?\b",
    "Urszulin": r"urszulin", "Zapole": r"zapol", "Budki Kozerkowskie": r"budk\w* kozerk",
    "Chawłowo": r"chawlow", "Kozery-Folwark": r"kozer\w*.folwark", "Lipy": r"\blip(?:y|ach)\b",
    "Mieczysławów": r"mieczyslaw", "Podchyliczki": r"podchylicz", "Putka": r"\bputk",
    "Wandzin": r"wandzin", "Zajączkowo": r"zajaczkow", "Żdżary": r"zdzar",
    # poza gminą
    "Milanówek": r"milanow", "Podkowa Leśna": r"podkow\w* lesn", "Jaktorów": r"jaktor",
    "Żabia Wola": r"zabi\w* wol", "Baranów": r"baranow", "Radziejowice": r"radziejowic",
    "Janki": r"\bjank", "Raszyn": r"raszyn", "Brwinów": r"brwinow", "Pruszków": r"pruszkow",
}
_PLACE_RE = [(n, re.compile(p)) for n, p in PLACES.items()]
# Jeśli znaleziono wariant dokładniejszy, pomijamy ogólniejszy.
_SUPERSEDED = {"Kozery Nowe": ["Kozery"], "Kozery-Folwark": ["Kozery"], "Izdebno Kościelne": [], }


def znajdz_miejsca(text, default=CALA_GMINA, limit=2):
    t = norm(text)
    found = []
    for name, rx in _PLACE_RE:
        m = rx.search(t)
        if m:
            found.append((m.start(), name))
    names = [n for _, n in sorted(found)]
    for specific, generic in _SUPERSEDED.items():
        if specific in names:
            names = [n for n in names if n not in generic]
    if names:
        return "|".join(names[:limit])
    if re.search(r"\bgrodzisk", t) and default == CALA_GMINA:
        return "Grodzisk Mazowiecki"
    return default


MONTHS = {"stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6,
          "lipca": 7, "sierpnia": 8, "wrzesnia": 9, "pazdziernika": 10, "listopada": 11,
          "grudnia": 12}
_DATE_WORD = re.compile(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")(?:\s+(20\d{2}))?\b")
_DATE_NUM = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})(?:\.(20\d{2}))?(?![\d])")
_TIME = re.compile(r"(?:godz\.?\s*|\bo\s+)(\d{1,2}):(\d{2})\b")


def wyciagnij_termin(text, today=None):
    """Zwraca (etykieta, data ISO) albo (None, None). Czyta tylko fakty: datę i godzinę."""
    today = today or date.today()
    t = norm(text)
    day = month = year = None
    m = _DATE_WORD.search(t)
    if m:
        day, month, year = int(m.group(1)), MONTHS[m.group(2)], m.group(3)
    else:
        m = _DATE_NUM.search(t)
        if m and 1 <= int(m.group(1)) <= 31 and 1 <= int(m.group(2)) <= 12:
            day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
    if day is None:
        return None, None
    y = int(year) if year else today.year
    try:
        d = date(y, month, day)
    except ValueError:
        return None, None
    if not year and (today - d).days > 60:
        d = date(y + 1, month, day)
    label = f"{day}.{month:02d}" + (f".{d.year}" if d.year != today.year else "")
    tm = _TIME.search(t)
    if tm:
        label += f", godz. {int(tm.group(1))}:{tm.group(2)}"
    return label, d.isoformat()
