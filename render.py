"""Buduje index.html z zapisanych wpisów: jeden strumień od najważniejszych i najświeższych (bez losowania). Archiwum dzieli wpisy na kategorie."""
import html
from datetime import date
from pathlib import Path

from klasyfikacja import klucz_miejsca, miejsce_wpisu, w_gminie
from redakcja import data_ui, dzien, godzina, inny_region, miejsce_ui, opis, termin_ui

# Kolejność sekcji na stronie i w menu: najpierw to, co dzieje się w okolicy (wydarzenia), potem wiadomości.
# Puste kategorie nie są pokazywane (ostrzeżenie o dużej wadze i tak trafia na górę jako główny temat strony).
KIND_UI = {
    "wyd": ("Wydarzenia", "bg-kultura"),
    "inne": ("Wiadomości", "bg-neutralny"),
    "ost": ("Ostrzeżenia", "bg-alert"),
    "zdr": ("Zdarzenia", "bg-alert"),
    "inw": ("Inwestycje i przetargi", "bg-drogi"),
    "spo": ("Sport", "bg-sport"),
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

WEIGHT = {"ost": 5, "wyd": 2, "inw": 2, "spo": 1, "inne": 0}   # zdarzenia (zdr, waga -2) nie trafiają na górę strony, ale w strumieniu idą za resztą
BOCZNE = 2               # tyle wpisów obok głównego tematu
DNI = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
MIESIACE_DOP = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września",
                "października", "listopada", "grudnia"]
NAJNOWSZE = 5            # tyle pozycji w pasku "Najnowsze"
NA_START = 12             # tyle wpisów widać od razu w strumieniu aktualności (reszta po kliknięciu "Pokaż więcej")
MAX_W_KATEGORII = 12      # tyle najwyżej z jednej kategorii na stronie (reszta w archiwum), żeby jedna nie zalała reszty
SHOW_DAYS = 14
ZAWSZE_W_MENU = {"ost", "zdr"}   # te kategorie zostają w menu nawet puste (przyciemnione, z zerem); sekcji bez wpisów i tak nie ma
DNI_OSTRZEZEN = 3        # ostrzeżenia (pogoda, komunikaty kryzysowe) są aktualne krótko: potem idą do archiwum
BEZ_TERMINU_DNI = 3      # zapowiedź bez terminu pokazujemy tylko tuż po pojawieniu się
BEZ_TERMINU_MAX = 3


POKAZUJ_BEZ_NOTKI = set()       # rodzaje pokazywane nawet bez notki. Pusty zbiór = na stronie tylko wpisy z notką.
TYLKO_GMINA = True              # True: tylko gmina Grodzisk Mazowiecki (bez Milanówka, Podkowy, Pruszkowa itd.); False: też okolica
ZRODLA_OSTRZEZEN = {"kryzysowe"}  # ...ale tylko z tych lokalnych źródeł (z portali ogólnych ostrzeżenia też wymagają notki)


def z_notka(items):
    """Wpisy bez streszczenia nie trafiają na stronę ani do archiwum (zostają w danych i wracają, gdy dostaną notkę).
    Wpisy ręczne zawsze zostają."""
    out = []
    for i in items:
        if i.get("manual"):
            out.append(i)
        elif i.get("poza_okolica") or inny_region(i["title"]):
            continue                  # temat ogólnopolski albo z innego regionu
        elif TYLKO_GMINA and not w_gminie(miejsce_wpisu(i.get("source_id"), i["title"], i.get("text"), i["place"])):
            continue                  # miejscowość spoza gminy (albo nie rozpoznano miejsca)
        elif i.get("text") or (i["kind"] in POKAZUJ_BEZ_NOTKI and i.get("source_id") in ZRODLA_OSTRZEZEN):
            out.append(i)
    return out


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
        limit_dni = DNI_OSTRZEZEN if it["kind"] == "ost" else SHOW_DAYS
        if (wiek(it, today) <= limit_dni and not past_event) or upcoming:
            out.append(it)
    return out


def _swiezosc(it, today):
    """10 punktów dla wpisu z dzisiaj, 0 po 10 dniach. Wydarzenie, które się zbliża, jest "świeże" tak, jak bliski jest jego termin."""
    w = wiek(it, today)
    ev = it.get("event_iso")
    if ev and ev >= today.isoformat():
        w = min(w, (date.fromisoformat(ev) - today).days)
    return max(0, 10 - w)


def _punkty(it, today):
    return WEIGHT.get(it["kind"], -2) + _swiezosc(it, today) - (0 if w_gminie(it["place"]) else 6)


def wybierz_jedynke(items, today):
    return max(items, key=lambda i: _punkty(i, today)) if items else None


def e(s):
    return html.escape(str(s), quote=True)


def _czesci(it, today):
    """Wspólne kawałki kart: znacznik kategorii, data, miejscowość, notka, termin, źródło."""
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
        data = f'<span>{e(dzien(it["first_seen"]))}</span>' if not termin else ""
    znaczek = f'<span class="badge">{e(miejsce)}</span>' if miejsce else ""
    tekst = opis(it, today)
    opis_html = f'<p class="opis">{e(tekst)}</p>' if tekst else ""
    zrodlo = e(it["source"]) + (f' <span class="also">oraz {e(", ".join(it["also"]))}</span>' if it.get("also") else "")
    tag = f'<span class="tag t-{e(it["kind"])}">{e(label)}</span>'
    meta = f'<div class="meta-bar">{tag}{znaczek}{data}<span>{zrodlo}</span></div>'
    link = f'<a href="{e(it["url"])}" target="_blank" rel="noopener" class="read-more">Zobacz źródło &rarr;</a>'
    return bg, meta, opis_html, when, link


def karta(it, today, kopia=False):
    """Wpis w strumieniu: sam tekst, bez ramek. Kopia wyróżnionego wpisu jest ukryta i pokazuje się dopiero przy filtrze kategorii."""
    bg, meta, opis_html, when, link = _czesci(it, today)
    klasa, ukryta = ("portal-card copy", " hidden") if kopia else ("portal-card", "")
    return (f'<article class="{klasa}" data-kind="{e(it["kind"])}" data-place="{e(it["place"])}"{ukryta}>'
            f'<div class="card-body">{meta}<h3>{e(it["title"])}</h3>{opis_html}{when}{link}</div></article>')


def karta_glowna(it, today):
    """Główny temat strony: duży kolorowy blok (zamiast zdjęcia)."""
    bg, meta, opis_html, when, link = _czesci(it, today)
    return (f'<article class="portal-card hero {bg}" data-kind="{e(it["kind"])}" data-place="{e(it["place"])}">'
            f'{ikona(it["kind"])}<div class="hero-body">{meta}<h2>{e(it["title"])}</h2>{opis_html}{when}{link}</div></article>')


def karta_boczna(it, today):
    bg, meta, opis_html, when, link = _czesci(it, today)
    return (f'<article class="portal-card side" data-kind="{e(it["kind"])}" data-place="{e(it["place"])}">'
            f'<div class="card-body">{meta}<h3>{e(it["title"])}</h3>{opis_html}{when}{link}</div></article>')


def pasek_najnowszych(pool, today):
    """Pasek najnowszych wpisów (jak \"Nowe\" na portalach): data i tytuł, link do źródła."""
    najnowsze = sorted(pool, key=lambda i: (data_wpisu(i), i["first_seen"]), reverse=True)[:NAJNOWSZE]
    if not najnowsze:
        return ""
    poz = "".join(
        f'<a class="tick" href="{e(i["url"])}" target="_blank" rel="noopener" data-place="{e(i["place"])}">'
        f'<time datetime="{e(data_wpisu(i))}">{e(data_ui(data_wpisu(i), today))}</time> {e(i["title"])}</a>'
        for i in najnowsze)
    return f'<div class="ticker"><span class="ticker-label">Najnowsze</span><div class="ticker-list">{poz}</div></div>'


def pierwsza_strona(pool, today):
    """Główny temat + wpisy boczne. Zdarzenia policji nie są wyróżniane. Zwraca (html, wyróżnione wpisy)."""
    kandydaci = [i for i in pool if i["kind"] != "zdr"]
    glowny = wybierz_jedynke(kandydaci, today)
    if not glowny:
        return "", []
    reszta = sorted((i for i in kandydaci if i is not glowny), key=lambda i: -_punkty(i, today))[:BOCZNE]
    boczne = "".join(karta_boczna(i, today) for i in reszta)
    html_ = (f'<div class="front">{karta_glowna(glowny, today)}'
             f'<div class="front-side">{boczne}</div></div>')
    return html_, [glowny] + reszta


def filtry(items):
    places = sorted({p for i in items for p in i["place"].split("|") if p not in ("cała gmina", "okolica")},
                    key=klucz_miejsca)
    opts = '<option value="">Cała gmina</option>' + "".join(
        f'<option value="{e(p)}">{e(p)}</option>' for p in places)
    return f'<div class="filters"><label for="place">Miejscowość:</label><select id="place">{opts}</select></div>'


def nawigacja(po_rodzajach):
    """Filtr kategorii nad strumieniem: "Wszystko" oraz kategorie z wpisami i stałe (ostrzeżenia, zdarzenia)."""
    wszystkie = sum(len(v) for v in po_rodzajach.values())
    out = [f'<a class="cat-link c-all active" href="#feed" data-kind="">'
           f'<span class="cat-name">Wszystko</span> <span class="cat-count">{wszystkie}</span></a>']
    for k, (label, bg) in KIND_UI.items():
        n = len(po_rodzajach.get(k, []))
        if not n and k not in ZAWSZE_W_MENU:
            continue
        out.append(f'<a class="cat-link c-{k}{"" if n else " zero"}" href="#feed" data-kind="{k}"{" data-stale" if k in ZAWSZE_W_MENU else ""}>'
                   f'<span class="cat-name">{e(label)}</span> <span class="cat-count">{n}</span></a>')
    return '<nav class="cat-nav" aria-label="Filtr kategorii">' + "".join(out) + "</nav>"


def kolejnosc(kind, items, today):
    """Wydarzenia: najbliższe terminy najpierw; reszta kategorii: od najświeższych."""
    swieze = sorted(items, key=lambda i: date.fromisoformat(data_wpisu(i)).toordinal(), reverse=True)
    if kind != "wyd":
        return swieze
    nadchodzace = sorted((i for i in items if (i.get("event_iso") or "") >= today.isoformat()),
                         key=lambda i: i["event_iso"])
    reszta = [i for i in swieze if i not in nadchodzace]
    return nadchodzace + reszta


def strumien(pokazane, wyrozniane, today):
    """Jeden strumień aktualności: ważność i świeżość decydują o kolejności, kategoria to tylko znacznik na karcie."""
    if not pokazane:
        return ""
    uporzadkowane = sorted(pokazane, key=lambda i: (-_punkty(i, today), -date.fromisoformat(data_wpisu(i)).toordinal()))
    reszta = [i for i in uporzadkowane if not any(i is w for w in wyrozniane)]
    karty = "".join(karta(i, today, kopia=True) for i in wyrozniane) + "".join(karta(i, today) for i in reszta)
    return (f'<section class="kat c-feed" id="feed" data-start="{NA_START}">'
            f'<div class="kat-head"><h2>Aktualności</h2><span class="kat-count">{len(pokazane)}</span></div>'
            f'<div class="kat-grid feed-grid">{karty}</div>'
            f'<button type="button" class="more" hidden></button></section>')


def build(items, template_path, out_path, today=None):
    today = today or date.today()
    pool = widoczne(items, today)
    po_rodzajach = {k: kolejnosc(k, [i for i in pool if i["kind"] == k], today)[:MAX_W_KATEGORII] for k in KIND_UI}
    pokazane = [i for k in KIND_UI for i in po_rodzajach[k]]
    front, wyrozniane = pierwsza_strona(pokazane, today)
    miesiac = MIESIACE_DOP[today.month - 1]
    page = Path(template_path).read_text(encoding="utf-8")
    page = page.replace("<!-- DATE_PLACEHOLDER -->", f"{DNI[today.weekday()]}, {today.day} {miesiac}")
    page = page.replace("<!-- NAV_PLACEHOLDER -->", nawigacja(po_rodzajach))
    page = page.replace("<!-- FILTERS_PLACEHOLDER -->", filtry(pool))
    page = page.replace("<!-- TICKER_PLACEHOLDER -->", pasek_najnowszych(pokazane, today))
    page = page.replace("<!-- FRONT_PLACEHOLDER -->", front)
    page = page.replace("<!-- DYNAMIC_CARDS_PLACEHOLDER -->", strumien(pokazane, wyrozniane, today))
    page = page.replace("<!-- UPDATED_PLACEHOLDER -->", f"Ostatnia aktualizacja: {today.strftime('%d.%m.%Y')}")
    Path(out_path).write_text(page, encoding="utf-8")
    return pokazane


MIESIACE = ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec", "Sierpień",
            "Wrzesień", "Październik", "Listopad", "Grudzień"]

_ARCH_CSS = """
        .arch-link { font-size: 0.9rem; font-weight: 700; color: var(--accent); text-decoration: none; }
        .arch-tools { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1.5rem; }
        .arch-tools input { font: inherit; padding: 0.5rem 1rem; border-radius: 99px; border: 1px solid #cbd5e1; min-width: 16rem; flex: 1; max-width: 28rem; }
        .arch-kat { margin-top: 2.2rem; scroll-margin-top: 90px; }
        .arch-kat-h { display: flex; justify-content: space-between; align-items: center; margin: 0 0 0.4rem; padding-bottom: 0.35rem; border-bottom: 4px solid var(--c-inne); font-family: var(--cond); font-size: 1.5rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.02em; }
        .arch-kat.c-ost .arch-kat-h, .arch-kat.c-zdr .arch-kat-h { border-color: var(--c-ost); } .arch-kat.c-wyd .arch-kat-h { border-color: var(--c-wyd); }
        .arch-kat.c-inw .arch-kat-h { border-color: var(--c-inw); } .arch-kat.c-spo .arch-kat-h { border-color: var(--c-spo); }
        .arch-kat-h .arch-n { color: var(--text-muted); }
        .arch-month { font-size: 1rem; margin: 1.2rem 0 0.4rem; padding-bottom: 0.2rem; border-bottom: 1px solid #e2e8f0; color: var(--text-muted); }
        .arch-nav { margin: 0 0 0.5rem; }
        .arch-list { list-style: none; margin: 0; padding: 0; }
        .arch-list li { background: var(--card-bg); border: 1px solid #e2e8f0; border-radius: 12px; padding: 0.7rem 1rem; margin-bottom: 0.5rem; }
        .arch-meta { font-size: 0.8rem; color: var(--text-muted); display: flex; flex-wrap: wrap; gap: 0.6rem; }
        .arch-list a.t { font-weight: 700; color: var(--text-main); text-decoration: none; }
        .arch-list a.t:hover { color: var(--accent); text-decoration: underline; }
        .arch-list p { margin: 0.25rem 0 0; font-size: 0.92rem; color: var(--text-muted); }
        .arch-count { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 1rem; }
"""

_ARCH_JS = """
<script>
(function () {
  var q = document.getElementById('q'), k = document.getElementById('k'), cnt = document.getElementById('cnt');
  function f() {
    var t = q.value.toLowerCase().trim(), kind = k.value, n = 0;
    document.querySelectorAll('.arch-list li').forEach(function (li) {
      var ok = (!t || li.dataset.s.indexOf(t) > -1) && (!kind || li.dataset.kind === kind);
      li.hidden = !ok; if (ok) n++;
    });
    document.querySelectorAll('.arch-sub').forEach(function (g) {
      g.hidden = !g.querySelector('li:not([hidden])');
    });
    document.querySelectorAll('.arch-kat').forEach(function (g) {
      var m = g.querySelectorAll('li:not([hidden])').length;
      g.hidden = !m;
      g.querySelector('.arch-n').textContent = m;
      var a = document.querySelector('.arch-nav a[href="#' + g.id + '"]');
      if (a) { a.hidden = !m; a.querySelector('.cat-count').textContent = m; }
    });
    cnt.textContent = n + ' wpisów';
  }
  q.addEventListener('input', f); k.addEventListener('change', f); f();
})();
</script>
"""


def wiersz_archiwum(it, today):
    label = KIND_UI[it["kind"]][0]
    miejsce = miejsce_ui(it["place"])
    d = date.fromisoformat(data_wpisu(it))
    tekst = opis(it, today)
    auto = ""
    haystack = " ".join([it["title"], tekst, it["source"], miejsce, label]).lower()
    zauw = ""
    meta = (f'<span>{d.day}.{d.month:02d}.{d.year}{zauw}</span><span>{e(label)}</span>'
            + (f'<span>{e(miejsce)}</span>' if miejsce else "") + f'<span>{e(it["source"])}</span>')
    return (f'<li data-kind="{e(it["kind"])}" data-s="{e(haystack)}">'
            f'<a class="t" href="{e(it["url"])}" target="_blank" rel="noopener">{e(it["title"])}</a>'
            f'<div class="arch-meta">{meta}</div>'
            + (f'<p>{e(tekst)}{auto}</p>' if tekst else "") + '</li>')


def build_archive(items, shown, template_path, out_path, today=None):
    """Archiwum: wszystko, czego nie ma na stronie głównej, podzielone na kategorie (w nich miesiącami od najnowszych). Nic nie jest usuwane."""
    today = today or date.today()
    na_glownej = {id(i) for i in shown}
    reszta = sorted((i for i in items if id(i) not in na_glownej), key=data_wpisu, reverse=True)
    sekcje_arch, nav = [], []
    for k, (label, _bg) in KIND_UI.items():
        wpisy = [i for i in reszta if i["kind"] == k]
        if not wpisy:
            continue
        podgrupy, biezacy = [], None
        for it in wpisy:                      # w kategorii: miesiącami, od najnowszych
            d = date.fromisoformat(data_wpisu(it))
            if (d.year, d.month) != biezacy:
                biezacy = (d.year, d.month)
                podgrupy.append((f"{MIESIACE[d.month - 1]} {d.year}", []))
            podgrupy[-1][1].append(wiersz_archiwum(it, today))
        wnetrze = "".join(f'<div class="arch-sub"><h3 class="arch-month">{e(t)}</h3><ul class="arch-list">{"".join(r)}</ul></div>'
                          for t, r in podgrupy)
        sekcje_arch.append(f'<section class="arch-kat c-{k}" id="arch-{k}"><h2 class="arch-kat-h"><span>{e(label)}</span>'
                           f'<span class="arch-n">{len(wpisy)}</span></h2>{wnetrze}</section>')
        nav.append(f'<a class="cat-link c-{k}" href="#arch-{k}"><span class="cat-name">{e(label)}</span> '
                   f'<span class="cat-count">{len(wpisy)}</span></a>')
    body = "".join(sekcje_arch) or '<p class="empty">Archiwum jest jeszcze puste.</p>'
    nav_html = f'<nav class="cat-nav arch-nav" aria-label="Kategorie archiwum">{"".join(nav)}</nav>' if nav else ""
    kinds = [k for k in KIND_UI if any(i["kind"] == k for i in reszta)]
    opts = '<option value="">Wszystkie rodzaje</option>' + "".join(
        f'<option value="{k}">{e(KIND_UI[k][0])}</option>' for k in kinds)
    head = Path(template_path).read_text(encoding="utf-8").split("<body>")[0]
    head = head.replace("<title>Grodzisk lokalnie</title>", "<title>Archiwum – Grodzisk lokalnie</title>")
    head = head.replace("    </style>", _ARCH_CSS + "    </style>", 1)
    page = (head + '<body>\n<header><div class="header-container"><h1>Grodzisk<span> lokalnie</span> – archiwum</h1>'
            '<a class="arch-link" href="index.html">&larr; Strona główna</a></div></header>\n<main>'
            '<div class="arch-tools"><input id="q" type="search" placeholder="Szukaj w archiwum…" aria-label="Szukaj">'
            f'<select id="k" aria-label="Rodzaj">{opts}</select></div><div class="arch-count" id="cnt"></div>'
            f'{nav_html}{body}</main>\n<footer><p>Archiwum zawiera starsze wpisy zebrane z publicznych stron lokalnych instytucji i mediów. '
            'Pełne treści czytaj u wydawców.</p></footer>'
            f'{_ARCH_JS}</body></html>')
    Path(out_path).write_text(page, encoding="utf-8")
    return len(reszta)
