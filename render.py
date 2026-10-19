"""Buduje index.html z zapisanych wpisów (bez losowania, od najważniejszych i najświeższych)."""
import html
from datetime import date
from pathlib import Path

KIND_UI = {
    "ost": ("Ostrzeżenia", "bg-alert"),
    "zdr": ("Zdarzenia", "bg-alert"),
    "wyd": ("Wydarzenia", "bg-kultura"),
    "inw": ("Inwestycje i przetargi", "bg-drogi"),
    "spo": ("Sport", "bg-sport"),
    "inne": ("Wiadomości", "bg-neutralny"),
}
WEIGHT = {"ost": 5, "zdr": 3, "wyd": 2, "inw": 2, "spo": 1, "inne": 0}
MAX_CARDS = 14
SHOW_DAYS = 14


def data_wpisu(it):
    return it.get("published") or it["first_seen"]


def wiek(it, today):
    return (today - date.fromisoformat(data_wpisu(it))).days


def widoczne(items, today):
    """Wpisy z ostatnich dni oraz wydarzenia, które jeszcze się nie odbyły."""
    out = []
    for it in items:
        upcoming = (it.get("event_iso") or "") >= today.isoformat()
        past_event = it.get("event_iso") and it["event_iso"] < today.isoformat()
        if (wiek(it, today) <= SHOW_DAYS and not past_event) or upcoming:
            out.append(it)
    return out


def wybierz_jedynke(items, today):
    def score(it):
        return WEIGHT[it["kind"]] + max(0, 10 - wiek(it, today))
    fresh = [i for i in items if wiek(i, today) <= 3]
    return max(fresh, key=score) if fresh else None


def e(s):
    return html.escape(str(s), quote=True)


def miejsca_ui(place):
    return "Cała gmina" if place == "cała gmina" else place.replace("|", ", ")


def karta(it, hero=False):
    label, bg = KIND_UI[it["kind"]]
    when = f'<p class="when">Kiedy: {e(it["when"])}</p>' if it.get("when") else ""
    d = data_wpisu(it)
    return (
        f'<article class="portal-card{" hero-tile" if hero else ""}" data-kind="{e(it["kind"])}" data-place="{e(it["place"])}">'
        f'<div class="img-container {bg}"><div class="tile-category-text">{e(label)}</div></div>'
        f'<div class="card-body"><div class="meta-bar"><span class="badge">{e(miejsca_ui(it["place"]))}</span>'
        f'<time datetime="{e(d)}">{e(d[8:10])}.{e(d[5:7])}</time><span>{e(it["source"])}</span></div>'
        f'<h2>{e(it["title"])}</h2>{when}'
        f'<a href="{e(it["url"])}" target="_blank" rel="noopener" class="read-more">Zobacz źródło &rarr;</a>'
        f'</div></article>')


def filtry(items):
    kinds = [k for k in KIND_UI if any(i["kind"] == k for i in items)]
    places = sorted({p for i in items for p in i["place"].split("|")})
    chips = '<button class="chip on" data-kind="">Wszystko</button>' + "".join(
        f'<button class="chip" data-kind="{k}">{e(KIND_UI[k][0])}</button>' for k in kinds)
    opts = '<option value="">Cała okolica</option>' + "".join(
        f'<option value="{e(p)}">{e(miejsca_ui(p))}</option>' for p in places)
    return f'<div class="filters"><div class="chips">{chips}</div><select id="place" aria-label="Miejscowość">{opts}</select></div>'


def build(items, template_path, out_path, today=None):
    today = today or date.today()
    pool = widoczne(items, today)
    hero = wybierz_jedynke(pool, today)
    rest = [i for i in pool if i is not hero]
    rest.sort(key=lambda i: (i["kind"] != "ost", i["kind"] != "zdr", -date.fromisoformat(data_wpisu(i)).toordinal()))
    cards = ""
    if hero:
        cards += karta(hero, hero=True)
    cards += "".join(karta(i) for i in rest[:MAX_CARDS])
    if not cards:
        cards = '<p class="empty">Dziś nie znaleziono nowych informacji. Spróbuj ponownie później.</p>'
    page = Path(template_path).read_text(encoding="utf-8")
    page = page.replace("<!-- DYNAMIC_CARDS_PLACEHOLDER -->", cards)
    page = page.replace("<!-- FILTERS_PLACEHOLDER -->", filtry(pool))
    page = page.replace("<!-- UPDATED_PLACEHOLDER -->", f"Ostatnia aktualizacja: {today.strftime('%d.%m.%Y')}")
    Path(out_path).write_text(page, encoding="utf-8")
