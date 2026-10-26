"""Zasady redakcyjne w kodzie: zdarzenia bez danych osób, daty po polsku, opisy z faktów.

- Zdarzenia (rodzaj "zdr") dostają neutralny tytuł: rodzaj zdarzenia i miejsce, bez imion, wieku
  i stanu zdrowia osób. Oryginalny tytuł nie jest zapisywany. Szczegóły są pod linkiem do źródła.
- Daty: "D.MM" z dniem tygodnia, a bliskie jako "wczoraj / dzisiaj / jutro".
- Opisy pod tytułami składamy z danych (rodzaj, miejsce, termin, źródło), nigdy z cudzej treści.
"""
import re
from datetime import date

from klasyfikacja import norm

DNI = ["pon.", "wt.", "śr.", "czw.", "pt.", "sob.", "niedz."]

# Cechy, które zdradzają osobę poszkodowaną: wiek, stan zdrowia, kto ucierpiał.
_WRAZLIWE = re.compile(
    r"\b\d{1,2}[- ]?(?:letni\w*|latk\w*|lat\b)|w wieku \d|"
    r"spiaczk|ciezko ranny|ciezko ranna|ranny|ranna|ranni|zmarl|nie zyje|zginel|"
    r"reanimac|w stanie ciezkim|walczy o zycie|ofiar")

# Rodzaj zdarzenia z tytułu (tylko typ, bez szczegółów). Pierwsze trafienie wygrywa.
_TYPY = [
    (r"wypad|kolizj|potrac|zderzen", "Wypadek drogowy"),
    (r"pozar", "Pożar"),
    (r"kradziez|wlaman|rozboj|napad|pobit", "Przestępstwo"),
    (r"zatrzym|wpadl|oszust|pijan", "Interwencja policji"),
    (r"zagin", "Poszukiwania osoby"),
]


def wrazliwe(text):
    return bool(_WRAZLIWE.search(norm(text)))


def miejsce_ui(place):
    if place == "cała gmina":
        return "Cała gmina"
    if place == "okolica":
        return ""
    return place.replace("|", ", ")


def neutralny_tytul(title, place):
    t = norm(title)
    typ = next((name for rx, name in _TYPY if re.search(rx, t)), "Zdarzenie")
    if place == "cała gmina":
        return f"{typ} w gminie"
    if place == "okolica":
        return f"{typ} w okolicy"
    return f"{typ}: {miejsce_ui(place)}"


# ---------- daty ----------

def dzien(iso):
    d = date.fromisoformat(iso)
    return f"{DNI[d.weekday()]} {d.day}.{d.month:02d}"


def data_ui(iso, today):
    diff = (date.fromisoformat(iso) - today).days
    slowo = {0: "dzisiaj", -1: "wczoraj", 1: "jutro"}.get(diff)
    if slowo:
        return slowo
    d = date.fromisoformat(iso)
    return dzien(iso) + (f".{d.year}" if d.year != today.year else "")


def godzina(when):
    m = re.search(r"godz\.\s*(\d{1,2}:\d{2})", when or "")
    return m.group(1) if m else None


def termin_ui(it, today):
    """Np. 'sob. 25.10, godz. 18:00' albo 'jutro, godz. 18:00'. None, gdy wpis nie ma terminu."""
    if not it.get("event_iso"):
        return None
    out = data_ui(it["event_iso"], today)
    g = godzina(it.get("when"))
    return out + (f", godz. {g}" if g else "")


# ---------- opisy ----------

def opis(it, today):
    """Jedno zdanie z faktów. Pusty tekst, gdy nic nie wnosi ponad tytuł i znaczniki na karcie."""
    if it.get("text"):
        return it["text"]
    # bez notki napisanej własnymi słowami karta nie dostaje żadnego szablonu: tytuł, znaczniki i źródło mówią resztę
    return ""


# ---------- podobne tytuły z różnych źródeł ----------

_POMIJANE = {"oraz", "przez", "jest", "jako", "tego", "dla", "ktory", "ktora", "ktore", "nowe", "nowy", "nowa"}


def _rdzenie(title):
    out = set()
    for w in re.findall(r"[a-z0-9]+", norm(title)):
        if w.isdigit() and len(w) >= 2:
            out.add(w)                      # liczby (np. 800, 2026) są mocnym znacznikiem tematu
        elif len(w) >= 4 and w not in _POMIJANE:
            out.add(w[:4])
    return out


def podobne(a, b, prog=0.55):
    """Ten sam temat opisany innymi słowami przez inne źródło (wspólne rdzenie słów)."""
    ra, rb = _rdzenie(a), _rdzenie(b)
    wspolne = ra & rb
    return len(wspolne) >= 3 and len(wspolne) / len(ra | rb) >= prog


_OGOLNE_RDZENIE = {"kons", "prog", "wspo", "spot", "zapr", "mies", "gmin", "powi", "info", "ogło", "ogl"}   # słowa z każdego komunikatu urzędu


def podobne_luzno(a, b, prog=0.75):
    """Dwa tytuły o tym samym temacie, gdy jeden jest dłuższy: wspólne rdzenie to większość krótszego tytułu.
    Stosujemy tylko między różnymi źródłami. Ogólne słowa urzędowe (konsultacje, program, współpraca) nie liczą się
    jako wspólne, bo skleiłyby różne konsultacje."""
    ra, rb = _rdzenie(a), _rdzenie(b)
    wspolne = (ra & rb) - _OGOLNE_RDZENIE
    return len(wspolne) >= 3 and len(wspolne) / min(len(ra), len(rb)) >= prog


# ---------- tematy spoza okolicy ----------

_INNY_REGION = re.compile(r"\bwoj\.\s+(?!mazowiec)|\bwojew[oó]dzt\w*\s+(?!mazowiec)", re.I)


def inny_region(title):
    """Tytuł mówi wprost o innym województwie (np. 'alert RCB dla woj. lubelskiego'): to nie jest wiadomość lokalna."""
    return bool(_INNY_REGION.search(title or ""))

# wersja-kompletu: 2026-10-25-2
