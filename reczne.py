"""Warstwa ręczna: wpisy z pliku data/manual.json (np. z Facebooka, opracowane i zanonimizowane).

Format jednego wpisu:
  {"kind": "wydarzenie", "place": "Książenice", "date": "2026-10-25", "time": "18:00",
   "title": "Koncert w świetlicy wiejskiej", "text": "Wstęp wolny.", "url": "https://...", "source": "Facebook"}

Wymagane: kind, place, date, title, url. Opcjonalne: time (tylko dla wydarzeń), text, source.
Plik jest wczytywany przy każdym przebiegu, więc usunięcie wpisu z pliku usuwa go ze strony.
Błąd w pliku zatrzymuje przebieg z czytelnym komunikatem, a opublikowana strona zostaje bez zmian.
"""
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from klasyfikacja import PLACES, CALA_GMINA
from redakcja import wrazliwe

RODZAJE = {
    "ost": "ost", "ostrzezenie": "ost", "ostrzeżenie": "ost",
    "zdr": "zdr", "zdarzenie": "zdr",
    "wyd": "wyd", "wydarzenie": "wyd",
    "inw": "inw", "inwestycja": "inw", "inwestycje": "inw",
    "spo": "spo", "sport": "spo",
    "inne": "inne", "wiadomosc": "inne", "wiadomość": "inne",
}
MIEJSCA = set(PLACES) | {CALA_GMINA, "okolica", "Grodzisk Mazowiecki"}


class BladPliku(ValueError):
    pass


def _miejsca(value, nr):
    names = [p.strip() for p in str(value).split("|") if p.strip()]
    zle = [n for n in names if n not in MIEJSCA]
    if not names or zle:
        raise BladPliku(f"wpis {nr}: nieznana miejscowość {zle or value!r} (pisz dokładnie jak na stronie, "
                        f"kilka miejscowości łącz znakiem |)")
    return "|".join(names)


def wczytaj(path, today=None):
    today = today or date.today()
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "[]")
    except json.JSONDecodeError as e:
        raise BladPliku(f"manual.json nie jest poprawnym JSON-em: {e}")
    if not isinstance(data, list):
        raise BladPliku("manual.json musi być listą wpisów w nawiasach kwadratowych [ ... ]")

    out, urls = [], set()
    for nr, raw in enumerate(data, 1):
        if not isinstance(raw, dict):
            raise BladPliku(f"wpis {nr}: oczekiwano obiektu w klamrach {{ ... }}")
        brak = [k for k in ("kind", "place", "date", "title", "url") if not str(raw.get(k, "")).strip()]
        if brak:
            raise BladPliku(f"wpis {nr}: brakuje pól {', '.join(brak)}")
        kind = RODZAJE.get(str(raw["kind"]).strip().lower())
        if not kind:
            raise BladPliku(f"wpis {nr}: nieznany rodzaj {raw['kind']!r} (dozwolone: {', '.join(sorted(set(RODZAJE.values())))})")
        try:
            d = date.fromisoformat(str(raw["date"]).strip())
        except ValueError:
            raise BladPliku(f"wpis {nr}: data {raw['date']!r} powinna mieć postać RRRR-MM-DD")
        url = str(raw["url"]).strip()
        if not re.match(r"https?://", url):
            raise BladPliku(f"wpis {nr}: adres musi zaczynać się od http:// lub https://")
        if url in urls:
            raise BladPliku(f"wpis {nr}: ten adres już jest w pliku")
        urls.add(url)
        godz = str(raw.get("time", "")).strip()
        if godz and not re.fullmatch(r"\d{1,2}:\d{2}", godz):
            raise BladPliku(f"wpis {nr}: godzina {godz!r} powinna mieć postać GG:MM")
        title, text = str(raw["title"]).strip(), str(raw.get("text", "")).strip()
        if len(text) > 300:
            raise BladPliku(f"wpis {nr}: opis ma {len(text)} znaków, limit to 300")
        if kind == "zdr" and (wrazliwe(title) or wrazliwe(text)):
            raise BladPliku(f"wpis {nr}: zdarzenie zawiera wiek, stan zdrowia lub dane osoby poszkodowanej, "
                            f"opisz samo zdarzenie bez tych szczegółów")
        when = f"{d.day}.{d.month:02d}" + (f", godz. {int(godz.split(':')[0])}:{godz.split(':')[1]}" if godz else "")
        wydarzenie = kind == "wyd"
        out.append({
            "id": "r" + hashlib.sha1(url.encode()).hexdigest()[:11],
            "title": title, "url": url, "source": str(raw.get("source", "")).strip() or "Wpis redakcji",
            "first_seen": today.isoformat() if (wydarzenie or d > today) else d.isoformat(),
            "published": None if wydarzenie else d.isoformat(),
            "kind": kind, "place": _miejsca(raw["place"], nr),
            "when": when if wydarzenie else None, "event_iso": d.isoformat() if wydarzenie else None,
            "text": text, "manual": True, "neutral": kind == "zdr",
        })
    return out
