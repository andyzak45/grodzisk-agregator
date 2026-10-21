#!/usr/bin/env python3
"""Zbiera tytuły, daty i linki z lokalnych źródeł i buduje stronę.

Zasady:
  - uczciwy nagłówek User-Agent z adresem kontaktowym (zmienna BOT_CONTACT),
  - szanujemy robots.txt i robimy przerwy między zapytaniami,
  - zapisujemy tylko tytuł, link, datę i fakty (rodzaj, miejscowość, termin), bez cudzych opisów,
  - tytuły zdarzeń zastępujemy neutralnymi (bez imion, wieku i stanu zdrowia osób),
  - nie zastępujemy brakujących danych wymyślonymi wpisami.

Użycie:  python scraper.py [--all] [--only ID] [--render-only]
"""
import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

import render
import reczne
import streszczenia
from klasyfikacja import klasyfikuj_rodzaj, norm, wyciagnij_termin, znajdz_miejsca
from redakcja import neutralny_tytul, podobne

ROOT = Path(__file__).parent
STORE = ROOT / "data" / "items.json"
STATUS = ROOT / "data" / "status.json"
BOT_CONTACT = __import__("os").environ.get("BOT_CONTACT", "TWOJ_EMAIL")
USER_AGENT = f"GrodziskLokalnieBot/1.0 (agregator linków; kontakt: {BOT_CONTACT})"
MAX_BYTES = 2_000_000
MAX_AGE_DAYS = 30        # starszych wpisów (wg daty publikacji) nie bierzemy
KEEP_DAYS = 45           # tyle trzymamy wpisy w pliku danych
MAX_NOTEK = 30           # tyle notek pod tytułami piszemy na przebieg (koszt i czas)
MAX_SZCZEGOLOW = 25      # tyle podstron na przebieg otwieramy, żeby znaleźć brakujące daty
DUPLIKAT_DNI = 7         # w tym oknie szukamy tego samego tematu w innych źródłach

JUNK_WORDS = ["szukaj", "menu", "kontakt", "newsletter", "zaloguj", "cookies", "polityka",
              "deklaracja dostepnosci", "mapa strony", "regulamin", "rodo", "wyszukiwarka",
              "czytaj wiecej", "zobacz wszystkie", "przejdz do tresci", "facebook", "instagram",
              "youtube", "archiwum", "ciasteczka", "dostepnosc"]


class Fetcher:
    """Pobiera strony grzecznie: robots.txt, przerwy, limit rozmiaru, uczciwy User-Agent."""

    def __init__(self, delay=2.0, timeout=20):
        self.delay, self.timeout = delay, timeout
        self.robots, self.last = {}, {}
        self.strony = {}   # podstrony pobrane do szukania dat, używane też do notek

    def _open(self, url, timeout=None):
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT, "Accept-Language": "pl,en;q=0.5",
            "Accept-Encoding": "identity"})
        return urllib.request.urlopen(req, timeout=timeout or self.timeout)

    def allowed(self, url):
        p = urlparse(url)
        host = f"{p.scheme}://{p.netloc}"
        if host not in self.robots:
            rp = RobotFileParser()
            try:
                with self._open(host + "/robots.txt", timeout=10) as r:
                    rp.parse(r.read(MAX_BYTES).decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as e:
                rp.allow_all = e.code < 500
                rp.disallow_all = e.code >= 500
            except Exception:
                rp.allow_all = True
            self.robots[host] = rp
        return self.robots[host].can_fetch(USER_AGENT, url)

    def get(self, url):
        if not self.allowed(url):
            raise PermissionError("robots.txt zabrania pobierania")
        host = urlparse(url).netloc
        wait = self.delay - (time.time() - self.last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        try:
            with self._open(url) as r:
                charset = r.headers.get_content_charset() or "utf-8"
                return r.read(MAX_BYTES).decode(charset, "replace")
        finally:
            self.last[host] = time.time()


def czysty_tekst(s):
    return " ".join(s.split())


def to_junk(title):
    t = norm(title)
    return len(title) < 15 or any(w in t for w in JUNK_WORDS)


def rejestr(host):
    parts = host.lower().removeprefix("www.").split(".")
    return ".".join(parts[-3:] if host.endswith(".gov.pl") else parts[-2:])


def ta_sama_strona(url, base):
    return rejestr(urlparse(url).netloc) == rejestr(urlparse(base).netloc)


def data_z_url(url):
    m = re.search(r"/(20\d{2})/(\d{2})/(\d{2})/", url) or re.search(r"/(20\d{2})(\d{2})(\d{2})\d*/", url)
    return _iso(m.groups()) if m else None


def data_z_tekstu(text):
    m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b", text)
    return _iso((m.group(3), m.group(2), m.group(1))) if m else None


def _iso(ymd):
    try:
        return date(int(ymd[0]), int(ymd[1]), int(ymd[2])).isoformat()
    except ValueError:
        return None


def znajdz_feed(soup, base):
    for tag in soup.find_all("link", rel="alternate"):
        if re.search(r"rss|atom", tag.get("type", ""), re.I) and tag.get("href"):
            return urljoin(base, tag["href"])
    return None


def parsuj_feed(xml_text, base):
    """RSS 2.0 i Atom. Zwraca listę {title, url, published, desc}."""
    items = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return items
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        def get(*names):  # pierwszy znaleziony element (uwaga: pusty element XML jest "fałszywy" w Pythonie)
            for n in names:
                c = next((c for c in el if c.tag.split("}")[-1] == n), None)
                if c is not None:
                    return c
            return None
        title, link = get("title"), get("link")
        url = (link.get("href") if link is not None and link.get("href") else (link.text if link is not None else None))
        if title is None or not url or not (title.text or "").strip():
            continue
        pub = get("pubDate", "published", "updated")
        published = None
        if pub is not None and pub.text:
            try:
                published = parsedate_to_datetime(pub.text).date().isoformat()
            except (TypeError, ValueError):
                published = pub.text[:10] if re.match(r"20\d{2}-\d{2}-\d{2}", pub.text) else None
        desc = get("description", "summary")
        items.append({"title": czysty_tekst(title.text), "url": urljoin(base, url.strip()),
                      "published": published or data_z_url(url), "desc": (desc.text or "") if desc is not None else ""})
    return items


def parsuj_html(html, base, selector=None):
    soup = BeautifulSoup(html, "html.parser")
    nodes = soup.select(selector) if selector else soup.select("article")
    if not nodes:
        nodes = soup.find_all(["h2", "h3", "h4"])
    items, seen = [], set()
    for node in nodes:
        head = node if node.name in ("h1", "h2", "h3", "h4") else node.find(["h1", "h2", "h3", "h4"])
        if head is None:
            continue
        a = head.find("a") or head.find_parent("a") or (node.find("a") if node is not head else None)
        if a is None or not a.get("href") or a["href"].startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        title = czysty_tekst(head.get_text())
        url = urldefrag(urljoin(base, a["href"]))[0]
        if to_junk(title) or url in seen or url.rstrip("/") == base.rstrip("/") or not ta_sama_strona(url, base):
            continue
        seen.add(url)
        t = node.find("time")
        published = None
        if t is not None:
            published = (t.get("datetime") or "")[:10] if re.match(r"20\d{2}-\d{2}-\d{2}", t.get("datetime") or "") else data_z_tekstu(t.get_text())
        published = published or data_z_url(url) or data_z_tekstu(node.get_text(" ")) if node is not head else (data_z_url(url))
        items.append({"title": title, "url": url, "published": published, "desc": ""})
    return items


def id_wpisu(url):
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def tkey(title):
    """Skrót tytułu do wykrywania powtórek. Zapisujemy go zamiast tytułu, gdy tytuł jest zastąpiony."""
    return hashlib.sha1(norm(title).encode()).hexdigest()[:12]


def _iso_z(v):
    v = str(v or "").strip()
    return v[:10] if re.match(r"20\d{2}-\d{2}-\d{2}", v) else None


def _fragment_po(slowa, text):
    m = re.search(r"(?:" + slowa + r")\W{0,5}(.{0,45})", text, re.I | re.S)
    return m.group(1) if m else ""


def szczegoly(html, today=None):
    """Z podstrony wpisu: data publikacji i początek wydarzenia. Tylko dane strukturalne
    (JSON-LD, meta, <time>) i podpisy typu "Data publikacji:" lub "Termin:"."""
    today = today or date.today()
    soup = BeautifulSoup(html, "html.parser")
    out = {"published": None, "start": None, "time": None, "tekst": None}

    def szukaj(node):
        if isinstance(node, dict):
            out["published"] = out["published"] or _iso_z(node.get("datePublished"))
            if "Event" in str(node.get("@type", "")):
                out["start"] = out["start"] or _iso_z(node.get("startDate"))
            for v in node.values():
                szukaj(v)
        elif isinstance(node, list):
            for v in node:
                szukaj(v)

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            szukaj(json.loads(tag.string or ""))
        except (ValueError, TypeError):
            pass
    if not out["published"]:
        m = soup.find("meta", property="article:published_time") or soup.find("meta", itemprop="datePublished")
        out["published"] = _iso_z(m.get("content")) if m else None
    t = soup.find("time", datetime=True)
    out["time"] = _iso_z(t["datetime"]) if t else None
    page = soup.get_text("\n")
    pub_txt = wyciagnij_termin(_fragment_po(r"data publikacji|opublikowano|data dodania", page), today)[1]
    out["tekst"] = pub_txt
    ev_txt = wyciagnij_termin(_fragment_po(r"termin|kiedy|data wydarzenia", page), today)
    out["start_tekst"] = ev_txt
    return out


def uzupelnij(items, fetcher, store, src, budzet):
    """Dla nowych wpisów bez daty publikacji (i wydarzeń bez terminu) otwiera podstronę, w limicie na przebieg."""
    wydarzenia = src.get("kind") == "wyd"
    for it in items:
        if budzet["left"] <= 0:
            break
        if id_wpisu(it["url"]) in store:
            continue
        brak_daty = not it["published"]
        brak_terminu = wydarzenia and wyciagnij_termin(it["title"])[1] is None
        if not (brak_daty or brak_terminu):
            continue
        budzet["left"] -= 1
        try:
            strona = fetcher.get(it["url"])
            if hasattr(fetcher, "strony"):
                fetcher.strony[it["url"]] = strona
            d = szczegoly(strona)
        except Exception:
            continue
        if brak_daty:
            it["published"] = d["published"] or d["tekst"] or (None if wydarzenia else d["time"])
        if wydarzenia:
            it["start"] = d["start"] or d["time"] or d["start_tekst"][1]


def zbierz(src, fetcher, diag=None):
    html = fetcher.get(src["url"])
    soup = BeautifulSoup(html, "html.parser")
    items = []
    feed = src.get("feed") or znajdz_feed(soup, src["url"])
    if feed:
        try:
            items = [i for i in parsuj_feed(fetcher.get(feed), src["url"]) if not to_junk(i["title"])]
        except Exception:
            items = []
    if not items:
        items = parsuj_html(html, src["url"], src.get("selector"))
    skip = src.get("skip_url", [])
    items = [i for i in items if not any(p in i["url"] for p in skip)]
    if diag is not None:
        diag.update({"bajty": len(html), "article": len(soup.find_all("article")),
                     "naglowki": len(soup.find_all(["h2", "h3", "h4"])), "feed": bool(feed),
                     "tytul": (soup.title.get_text(strip=True) if soup.title else "")[:80],
                     "tekst": " ".join(soup.get_text(" ").split())[:160]})
    return items[: src.get("limit", 15)]


def wczytaj_store(sources=None):
    """Wczytuje zapisane wpisy i stosuje bieżące reguły (rodzaj, miejscowość, tytuły zdarzeń, wykluczenia),
    więc poprawka reguł działa też wstecz, a stare wpisy nie zachowują nieaktualnych tytułów."""
    if not STORE.exists():
        return {}
    zrodla = {s["id"]: s for s in sources or []}
    store = {}
    for i in json.loads(STORE.read_text(encoding="utf-8")):
        src = zrodla.get(i.get("source_id"))
        if src and any(p in i["url"] for p in src.get("skip_url", [])):
            continue
        if src and not i.get("neutral"):
            i["kind"] = klasyfikuj_rodzaj(i["title"], src.get("kind"))
            i["place"] = znajdz_miejsca(i["title"], src.get("place", "cała gmina"))
        if i["kind"] == "zdr" and not i.get("neutral"):
            i["tkey"] = tkey(i["title"])
            i["title"] = neutralny_tytul(i["title"], i["place"])
            i["neutral"] = True
        if i.get("opis_auto") and not streszczenia.ksztalt_ok(i.get("text")):
            for k in ("text", "opis_auto", "opis_proba"):     # zepsuta notka (np. ucięta): usuwamy i generujemy od nowa
                i.pop(k, None)
        store[i["id"]] = i
    return store


def zapisz_store(store, today):
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
    items = [i for i in store.values() if i["first_seen"] >= cutoff or (i.get("event_iso") or "") >= today.isoformat()]
    STORE.parent.mkdir(exist_ok=True)
    STORE.write_text(json.dumps(sorted(items, key=lambda i: i["first_seen"], reverse=True),
                                ensure_ascii=False, indent=1), encoding="utf-8")
    return items


def dodaj(store, items, src, today):
    nowe = 0
    klucze = {i.get("tkey") or tkey(i["title"]) for i in store.values()}
    for it in items:
        iid = id_wpisu(it["url"])
        klucz = tkey(it["title"])
        if iid in store or klucz in klucze:
            continue
        start = it.get("start")
        when, event_iso = wyciagnij_termin(it["title"] + " " + it.get("desc", ""), today)
        if not event_iso and start:
            d = date.fromisoformat(start)
            when, event_iso = f"{d.day}.{d.month:02d}", start
        if it["published"] and (today - date.fromisoformat(it["published"])).days > MAX_AGE_DAYS \
                and (event_iso or "") < today.isoformat():
            continue
        kind = klasyfikuj_rodzaj(it["title"], src.get("kind"))
        place = znajdz_miejsca(it["title"], src.get("place", "cała gmina"))
        neutral = kind == "zdr"
        title = neutralny_tytul(it["title"], place) if neutral else it["title"]
        # ten sam temat opisany przez inne źródło: dopisujemy źródło do istniejącego wpisu
        powtorka = next((o for o in store.values()
                         if o["source_id"] != src["id"]
                         and (today - date.fromisoformat(o["first_seen"])).days <= DUPLIKAT_DNI
                         and ((neutral and o.get("neutral") and o["title"] == title
                               and o["first_seen"] == today.isoformat() and o["place"] == place)
                              or (not neutral and not o.get("neutral") and podobne(o["title"], title)))), None)
        klucze.add(klucz)
        if powtorka:
            also = powtorka.setdefault("also", [])
            if src["name"] not in also and src["name"] != powtorka["source"]:
                also.append(src["name"])
            continue
        store[iid] = {
            "id": iid, "title": title, "url": it["url"], "source": src["name"], "source_id": src["id"],
            "first_seen": today.isoformat(), "published": it["published"], "kind": kind, "place": place,
            "when": when, "event_iso": event_iso, "tkey": klucz}
        if neutral:
            store[iid]["neutral"] = True
        nowe += 1
    return nowe


def na_czas(src, today, force):
    return force or src["freq"] == "daily" or (src["freq"] == "weekly" and today.weekday() == 0) \
        or (src["freq"] == "rare" and today.day == 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="pobierz też źródła tygodniowe i rzadkie")
    ap.add_argument("--only", help="pobierz tylko to źródło (id)")
    ap.add_argument("--render-only", action="store_true", help="tylko zbuduj stronę z zapisanych danych")
    args = ap.parse_args()
    today = date.today()
    sources = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    try:  # błąd w pliku ręcznym zatrzymuje przebieg przed jakąkolwiek zmianą strony
        reczne_wpisy = reczne.wczytaj(ROOT / "data" / "manual.json", today)
    except reczne.BladPliku as e:
        print(f"BŁĄD w data/manual.json: {e}")
        sys.exit(1)
    store, status = wczytaj_store(sources), {}

    if not args.render_only:
        fetcher = Fetcher()
        budzet = {"left": MAX_SZCZEGOLOW}
        ok = 0
        for src in sources:
            if not src.get("enabled", True) or (args.only and src["id"] != args.only):
                continue
            if not args.only and not na_czas(src, today, args.all):
                continue
            try:
                diag = {}
                items = zbierz(src, fetcher, diag)
                uzupelnij(items, fetcher, store, src, budzet)
                n = dodaj(store, items, src, today)
                status[src["id"]] = {"ok": True, "found": len(items), "new": n}
                if not items:
                    status[src["id"]].update({"uwaga": "strona odpowiada, ale parser nie znalazł wpisów", "diag": diag})
                ok += 1
            except Exception as e:  # błąd jednego źródła nie zatrzymuje reszty
                status[src["id"]] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            print(f"{src['id']:20} {status[src['id']]}")
        STATUS.parent.mkdir(exist_ok=True)
        STATUS.write_text(json.dumps({"run": datetime.now().isoformat(timespec="seconds"), "sources": status},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        if status and ok == 0:
            print("Żadne źródło nie odpowiedziało, nie publikuję nowej strony.")
            sys.exit(1)

    if not args.render_only:
        zrodla = {x["id"]: x for x in sources}
        n = streszczenia.dopisz(store, zrodla, fetcher, today, MAX_NOTEK)
        print(f"Dopisano {n} notek pod tytułami")
    r = streszczenia.zastosuj_reczne(store, ROOT / "data" / "opisy.json")
    if r:
        print(f"Zastosowano {r} notek z data/opisy.json")
    items = zapisz_store(store, today)
    wszystkie = items + reczne_wpisy
    pokazane = render.build(wszystkie, ROOT / "template.html", ROOT / "index.html", today)
    w_archiwum = render.build_archive(wszystkie, pokazane, ROOT / "template.html", ROOT / "archiwum.html", today)
    print(f"Zapisano {len(items)} wpisów automatycznych i {len(reczne_wpisy)} ręcznych, zbudowano index.html i archiwum.html ({w_archiwum} wpisów w archiwum)")


if __name__ == "__main__":
    main()
