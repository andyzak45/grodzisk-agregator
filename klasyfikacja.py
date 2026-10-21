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
# Wzorce to wyrażenia regularne na tekście bez polskich znaków; każdy zaczyna się od granicy słowa,
# a krótkie rdzenie mają jawne końcówki (np. "pozar" nie łapie już słowa "pozarzadowych").
KIND_RULES = [
    # uroczystości, szkolenia i ćwiczenia: zwykłe wiadomości, nie zdarzenia ani przetargi (wygrywają z regułami niżej)
    ("inne", [r"hold ", r"uroczysto", r"obchod", r"pamieci", r"upamietn", r"wreczen", r"szkolen", r"profilakty",
              r"obron\w* cywiln", r"cwiczen"]),
    ("ost", [r"ostrzez", r"alert", r"awari", r"brak pradu", r"brak wody", r"utrudnien", r"objazd",
             r"wscieklizn", r"ewakuac", r"komunikat kryzysow", r"zagrozeni\w* atakiem", r"alarm",
             r"wylaczen\w* (?:pradu|wody)"]),
    ("zdr", [r"zatrzym", r"wpadl", r"wypadek", r"wypadk", r"kolizj", r"pozar(?:u|ze|em|y|ow|\b)",
             r"kradziez", r"wlaman", r"potracon", r"potracen", r"rozboj", r"napad", r"pobit",
             r"zgin", r"nie zyje", r"smiertel", r"tragiczn", r"pijan", r"ranny", r"ranna", r"ranni",
             r"zaginion", r"interwencj"]),
    ("spo", [r"mecz", r"pilk", r"siatk", r"tenis", r"pogon", r"sparta", r"bogoria", r"liga", r"ligi",
             r"bieg", r"turniej", r"zawod(?:y|ach|nik|nicz)", r"koszyk", r"plywa", r"kort",
             r"mistrzostw", r"grand prix"]),
    ("wyd", [r"koncert", r"spektakl", r"warsztat", r"festiwal", r"spotkani", r"wystaw", r"seans",
             r"impre", r"jarmark", r"kiermasz", r"targi", r"piknik", r"wydarzeni", r"zapraszam",
             r"zajec", r"teatr", r"noc bibliotek", r"rajd", r"cosplay", r"stand-up"]),
    ("inw", [r"przetarg", r"inwestycj", r"remont", r"budow", r"przebudow", r"modernizacj", r"droga",
             r"drogi", r"drog ", r"chodnik", r"oswietlen", r"wodociag", r"kanalizac", r"uchwal",
             r"budzet", r"dofinansowan", r"plan ogoln", r"planu ogoln", r"sesj", r"umow", r"wniosk",
             r"konsultacj", r"rekultywac", r"parking", r"sciezk"]),
]
_KIND_RE = [(k, re.compile(r"\b(?:" + "|".join(pats) + ")")) for k, pats in KIND_RULES]

# Źródła z podpowiedzią "zdr" (policja) i "ost" (zarządzanie kryzysowe) publikują też dużo
# profilaktyki i szkoleń. Dla nich liczą się tylko rodzaje poniżej, reszta to zwykła wiadomość.
HINT_ALLOWED = {"zdr": {"ost", "zdr", "wyd", "inne"}, "ost": {"ost", "zdr", "wyd", "inne"}}


def klasyfikuj_rodzaj(title, hint=None):
    t = norm(title)
    allowed = HINT_ALLOWED.get(hint)
    for kind, rx in _KIND_RE:
        if allowed and kind not in allowed:
            continue
        if rx.search(t):
            return kind
    if hint in HINT_ALLOWED or hint == "inw":
        return "inne"       # "inw" tylko po słowie kluczowym, inaczej to zwykła wiadomość z urzędu
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
    "Wandzin": r"wandzin", "Dąbrówka": r"\bdabrowk", "Zajączkowo": r"zajaczkow", "Żdżary": r"zdzar",
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


# Poziomy wielkości miejscowości (spis GUS 2021, miasto GUS 2024). Służą do sortowania listy.
POZIOMY = {
    1: ["Grodzisk Mazowiecki"],
    2: ["Książenice"],
    3: ["Adamowizna", "Odrano-Wola", "Opypy", "Szczęsne"],
    4: ["Chrzanów Mały", "Czarny Las", "Janinów", "Kałęczyn", "Kozerki", "Kozery", "Natolin", "Radonie"],
    5: ["Chlebnia", "Chrzanów Duży", "Izdebno Kościelne", "Kady", "Kraśnicza Wola", "Makówka",
        "Marynin", "Mościska", "Tłuste", "Wólka Grodziska"],
    6: ["Adamów", "Kłudno Nowe", "Kłudno Stare", "Kozery Nowe", "Władków", "Wężyk", "Zabłotnia",
        "Żuków", "Izdebno Nowe", "Urszulin", "Zapole", "Kłudzienko", "Dąbrówka", "Budki Kozerkowskie",
        "Chawłowo", "Izdebno Małe", "Kozery-Folwark", "Lipy", "Mieczysławów", "Podchyliczki", "Putka",
        "Wandzin", "Zajączkowo", "Żdżary"],
}
_POZIOM = {n: lvl for lvl, names in POZIOMY.items() for n in names}


def w_gminie(place):
    """Czy wpis dotyczy gminy Grodzisk Mazowiecki (jej miejscowości albo całej gminy), a nie okolicy."""
    return any(p == CALA_GMINA or p in _POZIOM for p in place.split("|"))


def klucz_miejsca(name):
    """Sortowanie listy miejscowości: poziom (większe najpierw), potem alfabetycznie; spoza gminy na końcu."""
    return (_POZIOM.get(name, 7), norm(name))


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
