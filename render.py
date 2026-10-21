"""Buduje index.html z zapisanych wpisów (bez losowania, od najważniejszych i najświeższych)."""
import html
from datetime import date
from pathlib import Path

from klasyfikacja import klucz_miejsca, w_gminie
from redakcja import data_ui, dzien, godzina, miejsce_ui, opis, termin_ui

KIND_UI = {
    "ost": ("Ostrzeżenia", "bg-alert"),
    "zdr": ("Zdarzenia", "bg-alert"),
    "wyd": ("Wydarzenia", "bg-kultura"),
    "inw": ("Inwestycje i przetargi", "bg-drogi"),
    "spo": ("Sport", "bg-sport"),
    "inne": ("Wiadomości", "bg-neutralny"),
}

# Proste ikony liniowe 24x24 (własne, bez zewnętrznych plików).
_IKONY = {
    "ost": '<path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 10v5M12 17.5v.5"/>',
    "zdr": '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.5"/>',
    "wyd": '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "inw": '<path d="M3 20h18M5 20V9l7-5 7 5v11M9 20v-6h6v6"/>',
    "spo": '<circle cx="12" cy="12" r="9"/><path d="M12 3v18M3 12h18M5.6 5.6c3 3 3 10.8 0 12.8M18.4 5.6c-3 3-3 10.8 0 12.8"/>',
    "inne": '<path d="M4 5h13a2 2 0 0 1 2 2v12H6a2 2 0 0 1-2-2V5Z"/><path d="M8 9h7M8 13h7M8 16h4"/>',
}

WEIGHT = {"ost": 5, "zdr": 0, "wyd": 2, "inw": 2, "spo": 1, "inne": 0}   # zdarzenia nie są "jedynką dnia"
MAX_CARDS = 40
SHOW_DAYS = 14
BEZ_TERMINU_DNI = 3      # zapowiedź bez terminu pokazujemy tylko tuż po pojawieniu się
BEZ_TERMINU_MAX = 3


def ikona(kind):
    return (f'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_IKONY[kind]}</svg>')


def data_wpisu(it):
    """Data publikacji, a gdy źródło jej nie podaje: dzień, w którym wpis zauważył bot (osobno oznaczany)."""
    return it.get("published") or it["first_seen"]


def wiek(it, today):
    return (today - date.fromisoformat(data_wpisu(it))).days


def widoczne(items, today):
    """Wpisy z ostatnich dni oraz wydarzenia, które jeszcze się nie odbyły.
    Zapowiedzi bez terminu są słabą informacją, więc zostają krótko i w małej liczbie."""
    out, bez_terminu = [], 0
    for it in sorted(items, key=lambda i: i["first_seen"], reverse=True):
        if it["kind"] == "wyd" and not it.get("event_iso"):
            if wiek(it, today) > BEZ_TERMINU_DNI or bez_terminu >= BEZ_TERMINU_MAX:
                continue
            bez_terminu += 1
            out.append(it)
            continue
        upcoming = (it.get("event_iso") or "") >= today.isoformat()
        past_event = it.get("event_iso") and it["event_iso"] < today.isoformat()
        if (wiek(it, today) <= SHOW_DAYS and not past_event) or upcoming:
            out.append(it)
    return out


def wybierz_jedynke(items, today):
    def score(it):
        return WEIGHT[it["kind"]] + max(0, 10 - wiek(it, today)) - (0 if w_gminie(it["place"]) else 6)
    fresh = [i for i in items if wiek(i, today) <= 3 and i["kind"] != "zdr"]
    return max(fresh, key=score) if fresh else None


def e(s):
    return html.escape(str(s), quote=True)


def karta(it, today, hero=False):
    label, bg = KIND_UI[it["kind"]]
    miejsce = miejsce_ui(it["place"])
    termin = termin_ui(it, today)
    when = ""
    if termin:
        godz = godzina(it.get("when"))
        when = (f'<p class="when">Kiedy: <time datetime="{e(it["event_iso"])}" data-t="{e(godz or "")}">'
                f'{e(termin if it["event_iso"] else "")}</time></p>')
    if it.get("published"):
        data = (f'<time datetime="{e(it["published"])}">{e(data_ui(it["published"], today))}</time>'
                if not termin else "")
    else:
        data = f'<span class="zauwazono">zauważono {e(dzien(it["first_seen"]))}</span>' if not termin else ""
    znaczek = f'<span class="badge">{e(miejsce)}</span>' if miejsce else ""
    tekst = opis(it, today)
    auto = ' <span class="auto">Opis automatyczny.</span>' if it.get("opis_auto") else ""
    opis_html = f'<p class="opis">{e(tekst)}{auto}</p>' if tekst else ""
    zrodlo = e(it["source"]) + (f' <span class="also">oraz {e(", ".join(it["also"]))}</span>' if it.get("also") else "")
    return (
        f'<article class="portal-card{" hero-tile" if hero else ""}" data-kind="{e(it["kind"])}" data-place="{e(it["place"])}">'
        f'<div class="img-container {bg}">{ikona(it["kind"])}<div class="tile-category-text">{e(label)}</div></div>'
        f'<div class="card-body"><div class="meta-bar">{znaczek}{data}<span>{zrodlo}</span></div>'
        f'<h2>{e(it["title"])}</h2>{opis_html}{when}'
        f'<a href="{e(it["url"])}" target="_blank" rel="noopener" class="read-more">Zobacz źródło &rarr;</a>'
        f'</div></article>')


def filtry(items):
    kinds = [k for k in KIND_UI if any(i["kind"] == k for i in items)]
    places = sorted({p for i in items for p in i["place"].split("|") if p not in ("cała gmina", "okolica")},
                    key=klucz_miejsca)
    chips = '<button class="chip on" data-kind="">Wszystko</button>' + "".join(
        f'<button class="chip" data-kind="{k}">{e(KIND_UI[k][0])}</button>' for k in kinds)
    opts = '<option value="">Cała okolica</option>' + "".join(
        f'<option value="{e(p)}">{e(p)}</option>' for p in places)
    return f'<div class="filters"><div class="chips">{chips}</div><select id="place" aria-label="Miejscowość">{opts}</select></div>'


def build(items, template_path, out_path, today=None):
    today = today or date.today()
    pool = widoczne(items, today)
    hero = wybierz_jedynke(pool, today)
    rest = [i for i in pool if i is not hero]
    rest.sort(key=lambda i: (i["kind"] != "ost", i["kind"] != "zdr", -date.fromisoformat(data_wpisu(i)).toordinal()))
    cards = ""
    if hero:
        cards += karta(hero, today, hero=True)
    cards += "".join(karta(i, today) for i in rest[:MAX_CARDS])
    if not cards:
        cards = '<p class="empty">Dziś nie znaleziono nowych informacji. Spróbuj ponownie później.</p>'
    page = Path(template_path).read_text(encoding="utf-8")
    page = page.replace("<!-- DYNAMIC_CARDS_PLACEHOLDER -->", cards)
    page = page.replace("<!-- FILTERS_PLACEHOLDER -->", filtry(pool))
    page = page.replace("<!-- UPDATED_PLACEHOLDER -->", f"Ostatnia aktualizacja: {today.strftime('%d.%m.%Y')}")
    Path(out_path).write_text(page, encoding="utf-8")
