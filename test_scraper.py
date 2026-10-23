import sys
import tempfile
import unittest
from unittest import mock
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
import urllib.error
import grafiki
import zdjecia_commons as zc
import render
import reczne
import redakcja
import scraper
import streszczenia
from klasyfikacja import klasyfikuj_rodzaj, klucz_miejsca, wyciagnij_termin, znajdz_miejsca

TODAY = date(2026, 10, 19)


class Rodzaj(unittest.TestCase):
    def test_reguly(self):
        cases = {
            "Policja zatrzymała oszustów": "zdr",
            "Przetarg na przebudowę stadionu": "inw",
            "Koncert w Mediatece": "wyd",
            "Mecz Pogoń Grodzisk – Polonia Warszawa": "spo",
            "Utrudnienia na linii WKD": "ost",
            "Spotkanie z planistami w Willi Niespodzianka": "wyd",
            "Projekt planu ogólnego udostępniony": "inw",
        }
        for title, kind in cases.items():
            self.assertEqual(klasyfikuj_rodzaj(title), kind, title)

    def test_podpowiedz_zrodla_gdy_brak_regul(self):
        self.assertEqual(klasyfikuj_rodzaj("Nowa dyrektor szkoły", hint="inw"), "inne")  # urząd bez słowa kluczowego to zwykła wiadomość
        self.assertEqual(klasyfikuj_rodzaj("Nowa dyrektor szkoły"), "inne")

    def test_brak_falszywych_trafien_w_srodku_slowa(self):
        # dawny bot uznawał podciąg "ue" i "zl" za kategorię; tu liczą się początki słów
        self.assertEqual(klasyfikuj_rodzaj("Wieczorne rozmowy o historii Grodziska"), "inne")


class Miejsca(unittest.TestCase):
    def test_odmiana(self):
        self.assertEqual(znajdz_miejsca("Plac zabaw we Władkowie"), "Władków")
        self.assertEqual(znajdz_miejsca("Spotkanie mieszkańców w Książenicach"), "Książenice")

    def test_dwa_miejsca(self):
        self.assertEqual(znajdz_miejsca("Droga w Natolinie i Chrzanowie Dużym"), "Natolin|Chrzanów Duży")

    def test_inna_gmina(self):
        self.assertEqual(znajdz_miejsca("Mural w Milanówku jest gotowy"), "Milanówek")

    def test_kozery_nowe_nie_dubluje_kozer(self):
        self.assertEqual(znajdz_miejsca("Zebranie w Kozerach Nowych"), "Kozery Nowe")

    def test_domyslne(self):
        self.assertEqual(znajdz_miejsca("Uchwała rady gminy"), "cała gmina")
        self.assertEqual(znajdz_miejsca("Uchwała rady miejskiej w Grodzisku"), "Grodzisk Mazowiecki")
        self.assertEqual(znajdz_miejsca("Koncert", default="okolica"), "okolica")


class Termin(unittest.TestCase):
    def test_slowna_data_i_godzina(self):
        self.assertEqual(wyciagnij_termin("Koncert 25 października o godz. 18:00", TODAY)[0], "25.10, godz. 18:00")

    def test_numeryczna(self):
        self.assertEqual(wyciagnij_termin("Spotkanie 26.10 w Willi", TODAY), ("26.10", "2026-10-26"))

    def test_brak_daty_i_bledna_data(self):
        self.assertEqual(wyciagnij_termin("Nowy plac zabaw", TODAY), (None, None))
        self.assertEqual(wyciagnij_termin("Wersja 45.13", TODAY), (None, None))

    def test_data_z_poczatku_roku_idzie_na_nastepny_rok(self):
        self.assertEqual(wyciagnij_termin("Bal 14 stycznia", TODAY)[1], "2027-01-14")


HTML = """
<html><body>
<nav><h3><a href="/menu">Menu główne strony</a></h3></nav>
<article><h2><a href="/2026/10/16/trzy-projekty/">Trzy projekty z unijnym dofinansowaniem</a></h2>
  <time datetime="2026-10-16T09:00:00+02:00">16 października</time></article>
<article><h2><a href="https://reklama.example.com/x">Kup teraz super ofertę dla Ciebie</a></h2></article>
<article><h2><a href="/20261017459853/pogon-polonia">Pogoń Grodzisk przegrała z Polonią Warszawa</a></h2></article>
<article><h2><a href="/kontakt">Kontakt</a></h2></article>
</body></html>
"""

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Przebudowa drogi w Natolinie</title><link>https://grodzisk.pl/droga-natolin/</link>
<pubDate>Thu, 15 Oct 2026 08:00:00 +0200</pubDate><description>Opis, który nie jest zapisywany</description></item>
<item><title></title><link>https://grodzisk.pl/pusty/</link></item>
</channel></rss>"""


class Parsowanie(unittest.TestCase):
    def test_html_filtruje_smieci_i_obce_domeny(self):
        items = scraper.parsuj_html(HTML, "https://grodzisk.pl/")
        titles = [i["title"] for i in items]
        self.assertEqual(titles, ["Trzy projekty z unijnym dofinansowaniem",
                                  "Pogoń Grodzisk przegrała z Polonią Warszawa"])

    def test_daty_z_time_i_z_adresu(self):
        items = scraper.parsuj_html(HTML, "https://grodzisk.pl/")
        self.assertEqual(items[0]["published"], "2026-10-16")
        self.assertEqual(items[1]["published"], "2026-10-17")

    def test_feed(self):
        items = scraper.parsuj_feed(RSS, "https://grodzisk.pl/")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published"], "2026-10-15")

    def test_znajdz_feed(self):
        soup = scraper.BeautifulSoup('<link rel="alternate" type="application/rss+xml" href="/feed/">', "html.parser")
        self.assertEqual(scraper.znajdz_feed(soup, "https://grodzisk.pl/x/"), "https://grodzisk.pl/feed/")

    def test_ta_sama_strona(self):
        self.assertTrue(scraper.ta_sama_strona("https://zarzadzaniekryzysowe.grodzisk.pl/a", "https://grodzisk.pl/"))
        self.assertFalse(scraper.ta_sama_strona("https://inny.pl/a", "https://grodzisk.pl/"))
        self.assertFalse(scraper.ta_sama_strona("https://bip.gov.pl/a", "https://grodzisk.policja.gov.pl/"))


class Magazyn(unittest.TestCase):
    def test_dodawanie_bez_duplikatow_i_starych_wpisow(self):
        store = {}
        src = {"id": "t", "name": "Test", "kind": "inne", "place": "cała gmina"}
        items = [
            {"title": "Koncert 25 października w Mediatece", "url": "https://x.pl/a", "published": "2026-10-18", "desc": ""},
            {"title": "Koncert 25 października w Mediatece", "url": "https://x.pl/b", "published": "2026-10-18", "desc": ""},
            {"title": "Bardzo stary wpis sprzed miesięcy", "url": "https://x.pl/c", "published": "2026-06-01", "desc": ""},
        ]
        self.assertEqual(scraper.dodaj(store, items, src, TODAY), 1)
        wpis = next(iter(store.values()))
        self.assertEqual((wpis["kind"], wpis["when"]), ("wyd", "25.10"))


class Strona(unittest.TestCase):
    def test_render_escapuje_i_pomija_minione_wydarzenia(self):
        items = [
            {"id": "1", "title": "<script>alert(1)</script> Koncert", "url": "https://x.pl/?a=1&b=2", "source": "Test",
             "first_seen": "2026-10-18", "published": "2026-10-18", "kind": "wyd", "place": "Władków",
             "when": "25.10", "event_iso": "2026-10-25"},
            {"id": "2", "title": "Wczorajszy koncert", "url": "https://x.pl/2", "source": "Test",
             "first_seen": "2026-10-17", "published": "2026-10-17", "kind": "wyd", "place": "cała gmina",
             "when": "18.10", "event_iso": "2026-10-18"},
        ]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "index.html"
            render.build(items, Path(__file__).resolve().parent / "template.html", out, TODAY)
            page = out.read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("Wczorajszy koncert", page)
        self.assertIn("Kiedy: <time", page)
        self.assertIn("niedz. 25.10", page)
        self.assertIn('data-place="Władków"', page)
        self.assertNotIn("PLACEHOLDER", page)


class Pobieranie(unittest.TestCase):
    def test_robots_blokuje_i_przepuszcza(self):
        import io
        f = scraper.Fetcher(delay=0)

        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False

        f._open = lambda url, timeout=None: R(b"User-agent: *\nDisallow: /prywatne/\n")
        self.assertFalse(f.allowed("https://x.pl/prywatne/a"))
        self.assertTrue(f.allowed("https://x.pl/aktualnosci/a"))

    def test_caly_przebieg_na_atrapie_sieci(self):
        src = {"id": "t", "name": "Test", "url": "https://grodzisk.pl/", "kind": "inw", "place": "cała gmina", "freq": "daily"}

        class Fake:
            def get(self, url):
                return HTML

        items = scraper.zbierz(src, Fake())
        store = {}
        self.assertEqual(scraper.dodaj(store, items, src, TODAY), 2)
        kinds = sorted(i["kind"] for i in store.values())
        self.assertEqual(kinds, ["inw", "spo"])


class RodzajNaPrawdziwychTytulach(unittest.TestCase):
    """Przypadki z pierwszego przebiegu bota (19.10.2026)."""

    def test_pozarzadowe_to_nie_pozar(self):
        self.assertEqual(klasyfikuj_rodzaj("Spotkanie dla organizacji pozarządowych", "wyd"), "wyd")
        self.assertEqual(klasyfikuj_rodzaj("Pożar hali w Kozerkach"), "zdr")

    def test_profilaktyka_policji_to_zwykla_wiadomosc(self):
        for t in ["Jeździsz rowerem – włóż kask, chroń swoją głowę!",
                  "Pieszy też może stworzyć zagrożenie! Czy znasz te przepisy?",
                  "Uważaj na dezinformację, rozmawiaj i wspieraj, a zagrożenia zgłaszaj Policji",
                  "Uczniowie grodziskiej „Jedynki” bezpieczni na drogach"]:
            self.assertEqual(klasyfikuj_rodzaj(t, "zdr"), "inne", t)

    def test_prawdziwe_zdarzenie_i_ostrzezenie_przechodza(self):
        self.assertEqual(klasyfikuj_rodzaj("Dwaj nieletni wpadli za oszustwo", "zdr"), "zdr")
        self.assertEqual(klasyfikuj_rodzaj("Zagrożenie atakiem z powietrza", "ost"), "ost")
        self.assertEqual(klasyfikuj_rodzaj("Bezpłatne szkolenia z obrony cywilnej", "ost"), "inne")


class Miejscowosci(unittest.TestCase):
    def test_kolejnosc_wg_wielkosci_potem_alfabetycznie(self):
        names = ["Żdżary", "Szczęsne", "Książenice", "Grodzisk Mazowiecki", "Adamowizna", "Milanówek", "Natolin"]
        self.assertEqual(sorted(names, key=klucz_miejsca),
                         ["Grodzisk Mazowiecki", "Książenice", "Adamowizna", "Szczęsne", "Natolin", "Żdżary", "Milanówek"])


class Redakcja(unittest.TestCase):
    def test_tytul_zdarzenia_bez_danych_ofiary(self):
        t = redakcja.neutralny_tytul("Tragiczny wypadek na DW719 w Kozerkach. 14-letnia Wiktoria w śpiączce", "Kozerki")
        self.assertEqual(t, "Wypadek drogowy: Kozerki")
        for zle in ("Wiktoria", "14", "śpiączk"):
            self.assertNotIn(zle, t)

    def test_wrazliwe(self):
        self.assertTrue(redakcja.wrazliwe("14-letnia dziewczyna w śpiączce"))
        self.assertTrue(redakcja.wrazliwe("Ranny 35-latek trafił do szpitala"))
        self.assertFalse(redakcja.wrazliwe("Koncert w Mediatece"))

    def test_daty_po_polsku(self):
        self.assertEqual(redakcja.data_ui("2026-10-19", TODAY), "dzisiaj")
        self.assertEqual(redakcja.data_ui("2026-10-18", TODAY), "wczoraj")
        self.assertEqual(redakcja.data_ui("2026-10-20", TODAY), "jutro")
        self.assertEqual(redakcja.data_ui("2026-10-25", TODAY), "niedz. 25.10")
        self.assertEqual(redakcja.data_ui("2026-10-17", TODAY), "sob. 17.10")
        self.assertEqual(redakcja.data_ui("2027-01-14", TODAY), "czw. 14.01.2027")

    def test_termin_z_godzina(self):
        it = {"event_iso": "2026-10-25", "when": "25.10, godz. 18:00"}
        self.assertEqual(redakcja.termin_ui(it, TODAY), "niedz. 25.10, godz. 18:00")

    def test_podobne_tytuly(self):
        self.assertTrue(redakcja.podobne("Podpisanie umowy na budowę oświetlenia oraz monitoringu",
                                         "Podpisano umowę na oświetlenie i monitoring ulic"))
        self.assertFalse(redakcja.podobne("Koncert w Mediatece", "Przetarg na przebudowę stadionu"))


class Zdarzenia(unittest.TestCase):
    SRC = {"id": "wpr", "name": "WPR24", "kind": "inne", "place": "okolica"}

    def test_oryginalny_tytul_nie_trafia_do_magazynu(self):
        store = {}
        items = [{"title": "Tragiczny wypadek na DW719 w Kozerkach. 14-letnia Wiktoria w śpiączce",
                  "url": "https://wpr24.pl/a", "published": "2026-10-18", "desc": ""}]
        self.assertEqual(scraper.dodaj(store, items, self.SRC, TODAY), 1)
        w = next(iter(store.values()))
        self.assertEqual((w["kind"], w["title"], w["place"]), ("zdr", "Wypadek drogowy: Kozerki", "Kozerki"))
        self.assertNotIn("Wiktoria", json.dumps(w, ensure_ascii=False))
        # drugi przebieg tego samego wpisu nie dubluje (rozpoznanie po skrócie tytułu)
        self.assertEqual(scraper.dodaj(store, [dict(items[0], url="https://wpr24.pl/inny-adres")], self.SRC, TODAY), 0)

    def test_stary_magazyn_jest_czyszczony_przy_wczytaniu(self):
        stary = [{"id": "x1", "title": "Tragiczny wypadek na DW719 w Kozerkach. 14-letnia Wiktoria w śpiączce, śledztwo w toku",
                  "url": "https://wpr24.pl/a", "source": "WPR24", "source_id": "wpr24", "first_seen": "2026-10-19",
                  "published": None, "kind": "zdr", "place": "Kozerki", "when": None, "event_iso": None}]
        with tempfile.TemporaryDirectory() as d:
            sciezka = Path(d) / "items.json"
            sciezka.write_text(json.dumps(stary, ensure_ascii=False), encoding="utf-8")
            orig, scraper.STORE = scraper.STORE, sciezka
            try:
                store = scraper.wczytaj_store([{"id": "wpr24", "kind": "inne", "place": "okolica"}])
            finally:
                scraper.STORE = orig
        w = store["x1"]
        self.assertEqual(w["title"], "Wypadek drogowy: Kozerki")
        self.assertTrue(w["neutral"])

    def test_ten_sam_temat_z_dwoch_zrodel_to_jeden_wpis(self):
        store = {}
        a = {"id": "um", "name": "Urząd Miejski", "kind": "inw", "place": "cała gmina"}
        b = {"id": "tm", "name": "Twoje Miasto", "kind": "inne", "place": "Grodzisk Mazowiecki"}
        scraper.dodaj(store, [{"title": "Podpisanie umowy na budowę oświetlenia oraz monitoringu",
                               "url": "https://grodzisk.pl/1", "published": "2026-10-13", "desc": ""}], a, TODAY)
        n = scraper.dodaj(store, [{"title": "Podpisano umowę na oświetlenie i monitoring ulic",
                                   "url": "https://tm.pl/1", "published": None, "desc": ""}], b, TODAY)
        self.assertEqual((n, len(store)), (0, 1))
        self.assertEqual(next(iter(store.values()))["also"], ["Twoje Miasto"])


class Szczegoly(unittest.TestCase):
    def test_json_ld_wydarzenie(self):
        html = ('<script type="application/ld+json">{"@type":"Event","startDate":"2026-10-25T18:00:00+01:00",'
                '"datePublished":"2026-10-10"}</script>')
        d = scraper.szczegoly(html, TODAY)
        self.assertEqual((d["published"], d["start"]), ("2026-10-10", "2026-10-25"))

    def test_meta_i_podpis_daty(self):
        self.assertEqual(scraper.szczegoly('<meta property="article:published_time" content="2026-10-17T08:00:00+02:00">',
                                           TODAY)["published"], "2026-10-17")
        self.assertEqual(scraper.szczegoly("<p>Data publikacji: 17.10.2026</p>", TODAY)["tekst"], "2026-10-17")

    def test_termin_z_podpisu(self):
        d = scraper.szczegoly("<p>Termin: 25 października, godz. 18:00</p>", TODAY)
        self.assertEqual(d["start_tekst"][1], "2026-10-25")

    def test_uzupelnienie_daty_z_podstrony(self):
        class F:
            def get(self, url):
                return "<p>Data publikacji: 17.10.2026</p>"
        it = {"title": "Komunikat Policji o zmianie organizacji ruchu", "url": "https://x.pl/a", "published": None, "desc": ""}
        scraper.uzupelnij([it], F(), {}, {"kind": "inne"}, {"left": 5})
        self.assertEqual(it["published"], "2026-10-17")

    def test_limit_podstron(self):
        class F:
            wywolania = 0
            def get(self, url):
                F.wywolania += 1
                return "<p>pusto</p>"
        its = [{"title": f"Wpis numer {i} bez daty", "url": f"https://x.pl/{i}", "published": None, "desc": ""} for i in range(10)]
        scraper.uzupelnij(its, F(), {}, {"kind": "inne"}, {"left": 3})
        self.assertEqual(F.wywolania, 3)


class Wykluczenia(unittest.TestCase):
    def test_skip_url(self):
        html = ('<article><h2><a href="/art-kraj/policja-w-szkolach-i1">Policja: sytuacja w szkołach się ustabilizowała</a></h2></article>'
                '<article><h2><a href="/art-miasto/krajowy-trening-i2">Krajowy Trening Rodzinny dla dzieci i rodziców</a></h2></article>')
        class F:
            def get(self, url):
                return html
        src = {"id": "t", "name": "T", "url": "https://t.twoje-miasto.pl/", "skip_url": ["/art-kraj/"]}
        self.assertEqual([i["title"] for i in scraper.zbierz(src, F())], ["Krajowy Trening Rodzinny dla dzieci i rodziców"])

    def test_diagnostyka_pustej_strony(self):
        class F:
            def get(self, url):
                return "<html><body><div>nic</div></body></html>"
        diag = {}
        self.assertEqual(scraper.zbierz({"id": "t", "name": "T", "url": "https://x.pl/"}, F(), diag), [])
        self.assertEqual((diag["article"], diag["naglowki"], diag["feed"]), (0, 0, False))


class WarstwaReczna(unittest.TestCase):
    def _wczytaj(self, dane):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "manual.json"
            p.write_text(json.dumps(dane, ensure_ascii=False), encoding="utf-8")
            return reczne.wczytaj(p, TODAY)

    BAZA = {"kind": "wydarzenie", "place": "Książenice", "date": "2026-10-25", "time": "18:00",
            "title": "Koncert w świetlicy", "text": "Wstęp wolny.", "url": "https://www.facebook.com/x/1"}

    def test_poprawny_wpis(self):
        w = self._wczytaj([self.BAZA])[0]
        self.assertEqual((w["kind"], w["when"], w["event_iso"], w["source"]),
                         ("wyd", "25.10, godz. 18:00", "2026-10-25", "Wpis redakcji"))

    def test_pusty_lub_brakujacy_plik(self):
        self.assertEqual(self._wczytaj([]), [])
        self.assertEqual(reczne.wczytaj(Path("/nie/ma/takiego.json"), TODAY), [])

    def test_bledy_maja_czytelny_komunikat(self):
        for zle, fragment in [
            (dict(self.BAZA, place="Atlantyda"), "nieznana miejscowość"),
            (dict(self.BAZA, date="25.10.2026"), "RRRR-MM-DD"),
            (dict(self.BAZA, kind="plotka"), "nieznany rodzaj"),
            (dict(self.BAZA, url="facebook.com/x"), "http"),
            (dict(self.BAZA, time="osiemnasta"), "GG:MM"),
            ({k: v for k, v in self.BAZA.items() if k != "title"}, "title"),
            (dict(self.BAZA, kind="zdarzenie", title="Wypadek, ranny 35-latek"), "wiek"),
        ]:
            with self.assertRaises(reczne.BladPliku) as ctx:
                self._wczytaj([zle])
            self.assertIn(fragment, str(ctx.exception))

    def test_zepsuty_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "manual.json"
            p.write_text('[{"kind": "sport",]', encoding="utf-8")
            with self.assertRaises(reczne.BladPliku):
                reczne.wczytaj(p, TODAY)


class StronaRedakcyjna(unittest.TestCase):
    def _strona(self, items):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "index.html"
            render.build(items, Path(__file__).resolve().parent / "template.html", out, TODAY)
            return out.read_text(encoding="utf-8")

    def _karty(self, page):
        """Liczba kart na stronie bez ukrytych kopii wyróżnionych wpisów (kopie służą tylko filtrowi kategorii)."""
        return page.count('<article class="portal-card') - page.count('<article class="portal-card copy')

    def _it(self, **kw):
        base = {"id": "1", "title": "Tytuł", "url": "https://x.pl/1", "source": "Źródło", "first_seen": "2026-10-19",
                "published": "2026-10-19", "kind": "inne", "place": "cała gmina", "when": None, "event_iso": None}
        base.update(kw)
        return base

    def test_zdarzenie_ma_opis_bez_szczegolow_i_nie_jest_jedynka(self):
        page = self._strona([self._it(kind="zdr", title="Wypadek drogowy: Kozerki", place="Kozerki", neutral=True)])
        self.assertNotIn("Sprawę opisuje", page)         # bez notki własnymi słowami karta nie ma szablonu
        self.assertNotIn("hero-tile\"", page)

    def test_menu_to_filtr_kategorii_a_ostrzezenia_i_zdarzenia_zostaja_w_menu(self):
        page = self._strona([self._it(kind="inw", title="Remont drogi")])
        self.assertIn('id="feed"', page)
        self.assertNotRegex(page, r'id="kat-')                # nie ma sekcji kategorii, jest jeden strumień
        self.assertIn('data-kind=""', page)                   # pozycja "Wszystko"
        self.assertIn('data-kind="inw"', page.split("<main>")[0])
        for k in ("wyd", "inne", "spo"):                      # puste kategorie: bez pozycji w menu
            self.assertNotIn(f'class="cat-link c-{k}', page)
        for k in ("ost", "zdr"):                              # stałe pozycje menu, przyciemnione
            self.assertIn(f'class="cat-link c-{k} zero"', page)

    def test_strumien_jest_sortowany_waznoscia_i_swiezoscia_a_nie_kategoria(self):
        items = [self._it(id="1", url="https://x.pl/1", kind="inne", title="Wiadomość stara", published="2026-10-12", first_seen="2026-10-12"),
                 self._it(id="2", url="https://x.pl/2", kind="inne", title="Wiadomość świeża"),
                 self._it(id="3", url="https://x.pl/3", kind="wyd", title="Wydarzenie jutro", event_iso="2026-10-20", when="20.10",
                          published="2026-10-14", first_seen="2026-10-14"),
                 self._it(id="4", url="https://x.pl/4", kind="inw", title="Inwestycja średnia", published="2026-10-16", first_seen="2026-10-16"),
                 self._it(id="5", url="https://x.pl/5", kind="ost", title="Ostrzeżenie dzisiaj")]
        page = self._strona(items)
        strumien = page[page.index('id="feed"'):]
        # kategorie się mieszają: wiadomość świeża idzie przed inwestycją, a zbliżające się wydarzenie przed starą wiadomością
        self.assertLess(strumien.index("Wiadomość świeża"), strumien.index("Inwestycja średnia"))
        self.assertLess(strumien.index("Wydarzenie jutro"), strumien.index("Wiadomość stara"))
        self.assertNotIn('class="kat c-inne"', page)

    def test_wyrozniony_wpis_ma_ukryta_kopie_w_strumieniu_dla_filtra(self):
        page = self._strona([self._it(id="1", url="https://x.pl/1", kind="ost", title="Ostrzeżenie dla gminy")])
        self.assertEqual(page.count("Ostrzeżenie dla gminy</h"), 2)       # hero + ukryta kopia
        self.assertIn('class="portal-card copy"', page)

    def test_pusta_strona_ma_komunikat(self):
        page = self._strona([])
        self.assertNotIn('<section class="kat', page)
        self.assertIn('id="brak"', page)

    def test_ostrzezenie_bez_terminu_wygasa_po_kilku_dniach(self):
        swieze = self._it(id="1", url="https://x.pl/1", kind="ost", title="Świeże ostrzeżenie",
                          first_seen="2026-10-18", published="2026-10-18")
        stare = self._it(id="2", url="https://x.pl/2", kind="ost", title="Stare ostrzeżenie",
                         first_seen="2026-10-10", published="2026-10-10")
        z_data_w_przyszlosci = self._it(id="3", url="https://x.pl/3", kind="ost", title="Ostrzeżenie do soboty",
                                        first_seen="2026-10-10", published="2026-10-10",
                                        event_iso="2026-10-24", when="24.10")
        z_data_minela = self._it(id="4", url="https://x.pl/4", kind="ost", title="Ostrzeżenie minione",
                                 first_seen="2026-10-17", published="2026-10-17",
                                 event_iso="2026-10-18", when="18.10")
        ids = {i["id"] for i in render.widoczne([swieze, stare, z_data_w_przyszlosci, z_data_minela], TODAY)}
        self.assertEqual(ids, {"1", "3"})

    def test_wydarzenia_najblizszy_termin_pierwszy(self):
        pozniej = self._it(id="a", url="https://x.pl/a", kind="wyd", title="Koncert grudniowy", event_iso="2026-12-05", when="5.12")
        wczesniej = self._it(id="b", url="https://x.pl/b", kind="wyd", title="Spotkanie listopadowe", event_iso="2026-11-02", when="2.11")
        page = self._strona([pozniej, wczesniej])
        self.assertLess(page.index("Spotkanie listopadowe"), page.index("Koncert grudniowy"))

    def test_kategoria_ma_limit_wpisow_na_stronie(self):
        items = [self._it(id=str(n), url=f"https://x.pl/{n}", title=f"Wiadomość numer {n}") for n in range(render.MAX_W_KATEGORII + 5)]
        page = self._strona(items)
        self.assertEqual(self._karty(page), render.MAX_W_KATEGORII)   # razem z główną i bocznymi

    def test_pierwsza_strona_ma_glowny_temat_date_i_pasek_najnowszych(self):
        items = [self._it(id="1", url="https://x.pl/1", kind="ost", title="Ostrzeżenie dla gminy"),
                 self._it(id="2", url="https://x.pl/2", kind="inw", title="Remont drogi"),
                 self._it(id="3", url="https://x.pl/3", kind="zdr", title="Interwencja policji", neutral=True)]
        page = self._strona(items)
        self.assertIn("poniedziałek, 19 października", page)
        self.assertIn('class="portal-card hero', page)
        self.assertIn('class="ticker"', page)
        glowna = page[page.index('class="portal-card hero'):page.index('class="front-side"')]
        self.assertIn("Ostrzeżenie dla gminy", glowna)
        self.assertNotIn("Interwencja policji", page[page.index('class="front"'):page.index('id="feed"')])

    def test_brak_podwojnej_kropki_po_skrocie_zrodla(self):
        it = self._it(kind="zdr", neutral=True, source="KPP Grodzisk Maz.")
        self.assertEqual(redakcja.opis(it, TODAY), "")

    def test_okolica_nie_jest_miejscowoscia_na_liscie(self):
        page = self._strona([self._it(place="okolica"), self._it(id="2", url="https://x.pl/2", place="Natolin")])
        self.assertNotIn('<option value="okolica">', page)
        self.assertIn('<option value="Natolin">', page)

    def test_lista_miejscowosci_wg_poziomu(self):
        items = [self._it(id=str(i), url=f"https://x.pl/{i}", place=p)
                 for i, p in enumerate(["Żdżary", "Książenice", "Szczęsne", "Grodzisk Mazowiecki"])]
        page = self._strona(items)
        kolejnosc = [page.index(f'<option value="{p}">') for p in ["Grodzisk Mazowiecki", "Książenice", "Szczęsne", "Żdżary"]]
        self.assertEqual(kolejnosc, sorted(kolejnosc))

    def test_wpis_bez_daty_jest_oznaczony_a_nie_udaje_dzisiejszego(self):
        page = self._strona([self._it(published=None, first_seen="2026-10-18")])
        glowna = page.split("<main>")[1].split("<script>")[0]
        self.assertNotIn("zauważono", page)         # bez dopisków w stylu bota
        self.assertIn("18.10", glowna)              # widać dzień, w którym wpis się pojawił
        self.assertNotIn("dzisiaj", glowna)

    def test_zapowiedzi_bez_terminu_sa_ograniczone(self):
        items = [self._it(id=str(i), url=f"https://x.pl/{i}", kind="wyd", title=f"Zapowiedź {i}") for i in range(6)]
        items.append(self._it(id="stara", url="https://x.pl/s", kind="wyd", title="Stara zapowiedź",
                              first_seen="2026-10-10", published=None))
        page = self._strona(items)
        self.assertEqual(self._karty(page), render.BEZ_TERMINU_MAX)
        self.assertNotIn("Stara zapowiedź", page)

    def test_wpis_reczny_pokazuje_wlasny_opis_i_grafike(self):
        page = self._strona([self._it(kind="inw", text="Zamknięta ulica Kościuszki do piątku.", manual=True)])
        self.assertIn("Zamknięta ulica Kościuszki do piątku.", page)
        self.assertIn('class="hero-ilu"', page)


class Notki(unittest.TestCase):
    ARTYKUL = ("Urząd Miejski informuje, że od poniedziałku 27 października zamknięta zostanie ulica Kościuszki "
               "na odcinku między ulicą Traugutta a ulicą Okólną. Powodem jest przebudowa sieci wodociągowej, "
               "którą prowadzi Zakład Wodociągów i Kanalizacji. Objazd wyznaczono ulicami Szkolną i Piękną, "
               "a prace potrwają do końca listopada. Autobusy linii 1 i 3 pojadą zmienioną trasą. ") * 2

    def _store(self, **kw):
        it = {"id": "a", "title": "Zamknięcie ulicy Kościuszki", "url": "https://grodzisk.pl/a", "source": "Urząd Miejski",
              "source_id": "um", "first_seen": "2026-10-19", "published": "2026-10-19", "kind": "inw",
              "place": "Grodzisk Mazowiecki", "when": None, "event_iso": None}
        it.update(kw)
        return {"a": it}

    class F:
        def __init__(self, html):
            self.html, self.strony, self.wywolania = html, {}, 0

        def get(self, url):
            self.wywolania += 1
            return self.html

    ZR = {"um": {"id": "um", "streszczaj": True}}

    def test_notka_trafia_do_wpisu(self):
        store = self._store()
        llm = lambda t: "Od 27 października przebudowa wodociągu zamknie ulicę Kościuszki, objazd pójdzie Szkolną i Piękną."
        n = streszczenia.dopisz(store, self.ZR, self.F(f"<article>{self.ARTYKUL}</article>"), TODAY, 5, llm)
        self.assertEqual(n, 1)
        self.assertTrue(store["a"]["opis_auto"])
        self.assertIn("przebudowa wodociągu", store["a"]["text"])

    def test_odrzuca_przepisany_fragment(self):
        store = self._store()
        llm = lambda t: "Powodem jest przebudowa sieci wodociągowej, którą prowadzi Zakład Wodociągów i Kanalizacji."
        n = streszczenia.dopisz(store, self.ZR, self.F(f"<article>{self.ARTYKUL}</article>"), TODAY, 5, llm)
        self.assertEqual(n, 0)
        self.assertNotIn("text", store["a"])
        self.assertTrue(store["a"]["opis_proba"])

    def test_odrzuca_dane_osob_brak_i_za_dlugie(self):
        for odp in ["Ranny 35-latek trafił do szpitala po wypadku na ulicy Kościuszki.", "BRAK", "x" * 400]:
            self.assertIsNone(streszczenia.sprawdz(odp, self.ARTYKUL), odp)

    def test_pomija_zdarzenia_zrodla_bez_flagi_i_stare_wpisy(self):
        f = self.F(f"<article>{self.ARTYKUL}</article>")
        llm = lambda t: "Od 27 października zamknięta zostanie ulica Kościuszki z powodu prac wodociągowych."
        for store, zr in [(self._store(kind="zdr"), self.ZR), (self._store(neutral=True), self.ZR),
                          (self._store(), {"um": {"id": "um"}}), (self._store(published="2026-10-01"), self.ZR)]:
            self.assertEqual(streszczenia.dopisz(store, zr, f, TODAY, 5, llm), 0)
        self.assertEqual(f.wywolania, 0)

    def test_krotka_strona_nie_idzie_do_modelu(self):
        wywolano = []
        llm = lambda t: wywolano.append(t) or "x"
        streszczenia.dopisz(self._store(), self.ZR, self.F("<article>Menu Aktualności Kontakt</article>"), TODAY, 5, llm)
        self.assertEqual(wywolano, [])

    def test_limit_i_brak_klucza(self):
        store = {str(i): dict(self._store()["a"], id=str(i), url=f"https://grodzisk.pl/{i}") for i in range(4)}
        llm = lambda t: "Od 27 października zamknięta zostanie ulica Kościuszki z powodu prac wodociągowych."
        self.assertEqual(streszczenia.dopisz(store, self.ZR, self.F(f"<article>{self.ARTYKUL}</article>"), TODAY, 2, llm), 2)
        import os
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("GITHUB_TOKEN", None)
        self.assertEqual(streszczenia.dopisz(self._store(), self.ZR, self.F(""), TODAY, 5), 0)

    def test_wybor_modelu(self):
        import os
        stare = {k: os.environ.pop(k, None) for k in ("ANTHROPIC_API_KEY", "GITHUB_TOKEN")}
        try:
            self.assertEqual(streszczenia.wybierz_model(), (None, 0))
            os.environ["GITHUB_TOKEN"] = "x"
            fn, przerwa = streszczenia.wybierz_model()
            self.assertTrue(fn and przerwa == streszczenia.PRZERWA)
            os.environ["ANTHROPIC_API_KEY"] = "sk-ant-y"
            self.assertEqual(streszczenia.wybierz_model()[1], 0)
        finally:
            for k in ("ANTHROPIC_API_KEY", "GITHUB_TOKEN"):
                os.environ.pop(k, None)
                if stare[k]:
                    os.environ[k] = stare[k]

    def test_limit_zapytan_konczy_notki_bez_oznaczania_wpisu(self):
        import urllib.error
        store = {str(i): dict(self._store()["a"], id=str(i), url=f"https://grodzisk.pl/{i}") for i in range(3)}
        def llm(t):
            raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        f = self.F(f"<article>{self.ARTYKUL}</article>")
        stare = streszczenia.LIMIT_CZEKANIE
        streszczenia.LIMIT_CZEKANIE = 0
        try:
            self.assertEqual(streszczenia.dopisz(store, self.ZR, f, TODAY, 5, llm), 0)
        finally:
            streszczenia.LIMIT_CZEKANIE = stare
        self.assertEqual(f.wywolania, 1)                       # po 429 i jednym ponowieniu koniec
        self.assertFalse(any(i.get("opis_proba") for i in store.values()))  # nic nie oznaczone, więc kolejny przebieg spróbuje znów

    def test_karta_nie_ma_dopisku_o_opisie_automatycznym(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "index.html"
            it = {"id": "1", "title": "Tytuł", "url": "https://x.pl/1", "source": "Źródło", "first_seen": "2026-10-19",
                  "published": "2026-10-19", "kind": "inw", "place": "Natolin", "when": None, "event_iso": None,
                  "text": "Od 27 października zamknięta zostanie ulica Kościuszki.", "opis_auto": True}
            render.build([it], Path(__file__).resolve().parent / "template.html", out, TODAY)
            page = out.read_text(encoding="utf-8")
        self.assertIn("ulica Kościuszki.", page)
        self.assertNotIn("Opis automatyczny.", page)
        self.assertNotIn("automatycznie", page)

class NotkiAwariaModelu(unittest.TestCase):
    N = Notki

    def _store(self, n=5):
        return {str(i): dict(Notki._store(Notki())["a"], id=str(i), url=f"https://grodzisk.pl/{i}") for i in range(n)}

    def test_pusta_odpowiedz_serwera_to_czytelny_blad(self):
        class R:
            status = 200
            def read(self): return b""
        with self.assertRaises(streszczenia.ModelBlad) as c:
            streszczenia._json_z_odpowiedzi(R())
        self.assertIn("pusta odpowiedź", str(c.exception))

    def test_awaria_modelu_nie_oznacza_wpisow_i_konczy_po_trzech(self):
        store = self._store()
        wywolania = []
        def llm(t):
            wywolania.append(1)
            raise streszczenia.ModelBlad("pusta odpowiedź serwera (status 200)")
        f = Notki.F(f"<article>{Notki.ARTYKUL}</article>")
        self.assertEqual(streszczenia.dopisz(store, Notki.ZR, f, TODAY, 30, llm), 0)
        self.assertEqual(len(wywolania), streszczenia.MAX_BLEDOW_Z_RZEDU)
        self.assertFalse(any(i.get("opis_proba") for i in store.values()))

    def test_stara_flaga_nie_blokuje_ponowienia(self):
        store = self._store(1)
        store["0"]["opis_proba"] = True      # ślad po przebiegach z awarią modelu
        llm = lambda t: "Od 27 października przebudowa wodociągu zamknie ulicę Kościuszki, objazd pójdzie Szkolną i Piękną."
        f = Notki.F(f"<article>{Notki.ARTYKUL}</article>")
        self.assertEqual(streszczenia.dopisz(store, Notki.ZR, f, TODAY, 5, llm), 1)

    def test_notki_reczne_z_pliku(self):
        import json, tempfile, os
        store = self._store(2)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "opisy.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump({"https://grodzisk.pl/0": "Od poniedziałku zamknięta będzie ulica Kościuszki z powodu prac.",
                           "https://grodzisk.pl/1": "Ranny 35-latek trafił do szpitala po wypadku."}, fh)
            self.assertEqual(streszczenia.zastosuj_reczne(store, p), 1)
        self.assertTrue(store["0"]["opis_auto"])
        self.assertNotIn("text", store["1"])

    def test_github_przechodzi_na_kolejny_wariant_gdy_serwer_odpowiada_ok(self):
        stare = streszczenia._otworz
        wywolane = []
        def falsz(req, timeout):
            wywolane.append(req.full_url + "|" + req.get_header("Accept"))
            if len(wywolane) < 3:
                raise streszczenia.ModelBlad("odpowiedź nie jest JSON-em (status 200): b'OK\\r\\n'")
            return {"choices": [{"message": {"content": "Notka testowa o dwóch zdaniach."}}]}
        streszczenia._otworz = falsz
        streszczenia._dzialajacy.clear()
        try:
            self.assertEqual(streszczenia.wywolaj_github("t", "tok"), "Notka testowa o dwóch zdaniach.")
            self.assertEqual(len(wywolane), 3)
            streszczenia.wywolaj_github("t", "tok")      # drugi raz od razu działający wariant
            self.assertEqual(len(wywolane), 4)
        finally:
            streszczenia._otworz = stare
            streszczenia._dzialajacy.clear()

    def test_brak_dns_to_blad_wariantu_a_nie_przerwanie(self):
        import urllib.request, socket
        stare = urllib.request.urlopen
        def zly(req, timeout=None):
            raise urllib.error.URLError(socket.gaierror(-2, "Name or service not known"))
        urllib.request.urlopen = zly
        streszczenia._dzialajacy.clear()
        try:
            with self.assertRaises(streszczenia.ModelBlad) as c:
                streszczenia.wywolaj_github("t", "tok")
            self.assertEqual(str(c.exception).count("wariant"), len(streszczenia.WARIANTY_GITHUB))
            self.assertIn("models.inference.ai.azure.com", str(c.exception))
        finally:
            urllib.request.urlopen = stare

    def test_gemini_proba_kolejnych_modeli_i_zapamietanie(self):
        stare = streszczenia._otworz
        adresy = []
        def falsz(req, timeout):
            adresy.append(req.full_url.split("/models/")[1])
            if len(adresy) == 1:
                raise streszczenia.ModelBlad("HTTP 404: model nie istnieje")
            return {"candidates": [{"content": {"parts": [{"text": "Notka "}, {"text": "z Gemini."}]}}]}
        streszczenia._otworz = falsz
        streszczenia._gemini_ok.clear(); streszczenia._gemini_martwe.clear()
        try:
            self.assertEqual(streszczenia.wywolaj_gemini("t", "klucz"), "Notka z Gemini.")
            self.assertEqual(adresy, ["gemini-3.5-flash:generateContent", "gemini-flash-latest:generateContent"])
            streszczenia.wywolaj_gemini("t", "klucz")
            self.assertEqual(adresy[-1], "gemini-flash-latest:generateContent")   # od razu działający model
            self.assertEqual(len(adresy), 3)
        finally:
            streszczenia._otworz = stare
            streszczenia._gemini_ok.clear(); streszczenia._gemini_martwe.clear()

    def test_wybor_gemini_przed_github(self):
        import os
        stare = {k: os.environ.pop(k, None) for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GITHUB_TOKEN")}
        try:
            os.environ["GITHUB_TOKEN"] = "x"
            os.environ["GEMINI_API_KEY"] = "g"
            self.assertEqual(streszczenia.wybierz_model()[1], streszczenia.PRZERWA_GEMINI)
        finally:
            for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GITHUB_TOKEN"):
                os.environ.pop(k, None)
                if stare[k]:
                    os.environ[k] = stare[k]

    def test_klucz_gemini_w_sekrecie_anthropic_jest_rozpoznany(self):
        import os
        stare = {k: os.environ.pop(k, None) for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GITHUB_TOKEN")}
        try:
            os.environ["ANTHROPIC_API_KEY"] = "AIzaSyTESTOWY"
            self.assertEqual(streszczenia.wybierz_model()[1], streszczenia.PRZERWA_GEMINI)
            os.environ["ANTHROPIC_API_KEY"] = "sk-ant-api03-xyz"
            self.assertEqual(streszczenia.wybierz_model()[1], 0)
        finally:
            for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GITHUB_TOKEN"):
                os.environ.pop(k, None)
                if stare[k]:
                    os.environ[k] = stare[k]

    def test_gemini_ponawia_przy_przeciazeniu_503(self):
        stare, stary_sen = streszczenia._otworz, streszczenia.time.sleep
        proby = []
        def falsz(req, timeout):
            proby.append(1)
            if len(proby) < 3:
                raise streszczenia.ModelBlad('HTTP 503: b\'{"status": "UNAVAILABLE"}\'')
            return {"candidates": [{"content": {"parts": [{"text": "Notka po ponowieniu."}]}}]}
        streszczenia._otworz, streszczenia.time.sleep = falsz, lambda s: None
        streszczenia._gemini_ok.clear(); streszczenia._gemini_martwe.clear()
        try:
            self.assertEqual(streszczenia.wywolaj_gemini("t", "klucz"), "Notka po ponowieniu.")
            self.assertEqual(len(proby), 3)       # dwa razy 503, trzecia próba tego samego modelu przeszła
        finally:
            streszczenia._otworz, streszczenia.time.sleep = stare, stary_sen
            streszczenia._gemini_ok.clear(); streszczenia._gemini_martwe.clear()

    def test_limit_minutowy_jedno_ponowienie_i_dalej(self):
        import urllib.error
        store = self._store(2)
        wywolania = []
        def llm(t):
            wywolania.append(1)
            if len(wywolania) == 1:
                raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
            return "Od 27 października przebudowa wodociągu zamknie ulicę Kościuszki, objazd pójdzie Szkolną i Piękną."
        f = Notki.F(f"<article>{Notki.ARTYKUL}</article>")
        stare = streszczenia.LIMIT_CZEKANIE
        streszczenia.LIMIT_CZEKANIE = 0
        try:
            self.assertEqual(streszczenia.dopisz(store, Notki.ZR, f, TODAY, 5, llm), 2)
        finally:
            streszczenia.LIMIT_CZEKANIE = stare

    def test_ksztalt_notki(self):
        self.assertFalse(streszczenia.ksztalt_ok("spotkaniach publicznych). * *"))          # prawdziwy urywek z Gemini
        self.assertFalse(streszczenia.ksztalt_ok("Urząd zaprasza na bezpłatne kursy obrony cywilnej w weekend"))  # bez kropki
        self.assertFalse(streszczenia.ksztalt_ok("**Urząd** zaprasza na bezpłatne kursy obrony cywilnej."))      # markdown
        self.assertTrue(streszczenia.ksztalt_ok("Urząd zaprasza na bezpłatne kursy obrony cywilnej w ten weekend."))

    def test_gemini_25_bez_myslenia_i_z_duzym_limitem(self):
        stare = streszczenia._otworz
        zlapane = []
        def falsz(req, timeout):
            zlapane.append(json.loads(req.data))
            return {"candidates": [{"content": {"parts": [{"text": "Całe zdanie testowe o czterech słowach więcej."}]}}]}
        streszczenia._otworz = falsz
        streszczenia._gemini_ok.clear(); streszczenia._gemini_martwe.clear()
        try:
            streszczenia.wywolaj_gemini("t", "klucz", model="gemini-2.5-flash")
        finally:
            streszczenia._otworz = stare
            streszczenia._gemini_ok.clear(); streszczenia._gemini_martwe.clear()
        cfg = zlapane[0]["generationConfig"]
        self.assertEqual(cfg["thinkingConfig"], {"thinkingBudget": 0})
        self.assertGreaterEqual(cfg["maxOutputTokens"], 1024)

    def test_zepsuta_notka_jest_czyszczona_przy_wczytaniu(self):
        import tempfile, pathlib
        wpis = dict(Notki._store(Notki())["a"], id="z1", url="https://grodzisk.pl/z1",
                    text="spotkaniach publicznych). * *", opis_auto=True, opis_proba="v2")
        dobry = dict(wpis, id="z2", url="https://grodzisk.pl/z2",
                     text="Urząd zaprasza na bezpłatne kursy obrony cywilnej w ten weekend.")
        stary = scraper.STORE
        with tempfile.TemporaryDirectory() as d:
            scraper.STORE = pathlib.Path(d) / "items.json"
            scraper.STORE.write_text(json.dumps([wpis, dobry]), encoding="utf-8")
            try:
                store = scraper.wczytaj_store([])
            finally:
                scraper.STORE = stary
        self.assertNotIn("text", store["z1"])
        self.assertNotIn("opis_proba", store["z1"])        # dostanie nową notkę
        self.assertIn("text", store["z2"])

    def test_gemini_limit_429_przechodzi_na_kolejny_model_a_gdy_wszystkie_to_429(self):
        stare = streszczenia._otworz
        adresy = []
        def falsz(req, timeout):
            adresy.append(req.full_url.split("/models/")[1].split(":")[0])
            if len(adresy) == 1:
                raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
            return {"candidates": [{"content": {"parts": [{"text": "Całe zdanie testowe o czterech słowach więcej."}]}}]}
        streszczenia._otworz = falsz
        streszczenia._gemini_ok.clear(); streszczenia._gemini_martwe.clear()
        try:
            self.assertTrue(streszczenia.wywolaj_gemini("t", "klucz"))
            self.assertEqual(adresy, ["gemini-3.5-flash", "gemini-flash-latest"])
            def wszystkie_429(req, timeout):
                raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
            streszczenia._otworz = wszystkie_429
            with self.assertRaises(urllib.error.HTTPError) as c:
                streszczenia.wywolaj_gemini("t", "klucz")
            self.assertEqual(c.exception.code, 429)
        finally:
            streszczenia._otworz = stare
            streszczenia._gemini_ok.clear(); streszczenia._gemini_martwe.clear()

    def test_ostrzezenie_bez_notki_nie_ma_szablonu(self):
        it = {"kind": "ost", "source": "Grodziski24"}
        self.assertEqual(redakcja.opis(it, TODAY), "")


class RodzajPoprawki(unittest.TestCase):
    def test_urzad_bez_slowa_kluczowego_to_wiadomosc_nie_inwestycja(self):
        self.assertEqual(klasyfikuj_rodzaj("Bezpłatne szkolenia z obrony cywilnej już w ten weekend", "inw"), "inne")
        self.assertEqual(klasyfikuj_rodzaj("Projekt planu ogólnego Gminy Grodzisk Mazowiecki", "inw"), "inw")

    def test_policja_hold_to_nie_zdarzenie(self):
        t = "Grodziscy policjanci oddali hołd Koledze, który zginął na służbie"
        self.assertEqual(klasyfikuj_rodzaj(t, "zdr"), "inne")
        self.assertEqual(klasyfikuj_rodzaj("Wypadek na DW719, jedna osoba ranna", "zdr"), "zdr")



if __name__ == "__main__":
    unittest.main()


class GeminiMartweModele(unittest.TestCase):
    def test_model_404_jest_pomijany_przy_kolejnych_wywolaniach(self):
        stare = streszczenia._otworz
        adresy = []
        def falsz(req, timeout):
            m = req.full_url.split("/models/")[1].split(":")[0]
            adresy.append(m)
            if m != "gemini-flash-lite-latest":
                raise streszczenia.ModelBlad("HTTP 404: model niedostepny")
            return {"candidates": [{"content": {"parts": [{"text": "Notka."}]}}]}
        streszczenia._otworz = falsz
        streszczenia._gemini_ok.clear(); streszczenia._gemini_martwe.clear()
        try:
            streszczenia.wywolaj_gemini("t", "k")
            n = len(adresy)
            streszczenia.wywolaj_gemini("t", "k")
            self.assertEqual(adresy[n:], ["gemini-flash-lite-latest"])
        finally:
            streszczenia._otworz = stare
            streszczenia._gemini_ok.clear(); streszczenia._gemini_martwe.clear()


class Archiwum(unittest.TestCase):
    def _wpis(self, i, dni_temu, **kw):
        d = (TODAY - timedelta(days=dni_temu)).isoformat()
        w = {"id": f"id{i}", "title": f"Tytuł {i}", "url": f"https://x.pl/{i}", "source": "Z", "source_id": "z",
             "first_seen": d, "published": d, "kind": "inne", "place": "Grodzisk Mazowiecki",
             "when": None, "event_iso": None, "tkey": f"k{i}"}
        w.update(kw)
        return w

    def test_archiwum_ma_wpisy_spoza_strony_glownej_i_nic_nie_ginie(self):
        stary = self._wpis(1, 60, text="Notka <b>starego</b>.", opis_auto=True)
        nowy = self._wpis(2, 1)
        items = [stary, nowy]
        with tempfile.TemporaryDirectory() as d:
            sz = Path(__file__).resolve().parent / "template.html"
            pokazane = render.build(items, sz, Path(d) / "index.html", TODAY)
            self.assertIn(nowy, pokazane)
            self.assertNotIn(stary, pokazane)
            n = render.build_archive(items, pokazane, sz, Path(d) / "archiwum.html", TODAY)
            page = (Path(d) / "archiwum.html").read_text(encoding="utf-8")
        self.assertEqual(n, 1)
        self.assertIn("Tytuł 1", page)
        self.assertNotIn("Tytuł 2", page)
        self.assertIn("&lt;b&gt;starego&lt;/b&gt;", page)      # treść jest escapowana
        self.assertNotIn("opis automatyczny", page)
        self.assertIn("index.html", page)

    def test_archiwum_jest_podzielone_na_kategorie_a_w_nich_na_miesiace(self):
        items = [self._wpis(1, 60, kind="wyd"), self._wpis(2, 70, kind="inne"), self._wpis(3, 65, kind="wyd"),
                 self._wpis(4, 1, kind="spo")]
        with tempfile.TemporaryDirectory() as d:
            sz = Path(__file__).resolve().parent / "template.html"
            pokazane = render.build(items, sz, Path(d) / "index.html", TODAY)
            render.build_archive(items, pokazane, sz, Path(d) / "archiwum.html", TODAY)
            page = (Path(d) / "archiwum.html").read_text(encoding="utf-8")
        for k in ("wyd", "inne"):
            self.assertIn(f'id="arch-{k}"', page)
        self.assertNotIn('id="arch-ost"', page)                 # kategoria bez wpisów w archiwum nie ma sekcji
        self.assertLess(page.index('id="arch-wyd"'), page.index('id="arch-inne"'))
        wyd = page[page.index('id="arch-wyd"'):page.index('id="arch-inne"')]
        self.assertIn("Tytuł 1", wyd)
        self.assertIn("Tytuł 3", wyd)
        self.assertNotIn("Tytuł 2", wyd)
        self.assertIn('class="arch-month"', page)
        self.assertIn('href="#arch-wyd"', page)                  # menu kategorii archiwum

    def test_puste_archiwum(self):
        with tempfile.TemporaryDirectory() as d:
            sz = Path(__file__).resolve().parent / "template.html"
            render.build_archive([], [], sz, Path(d) / "a.html", TODAY)
            self.assertIn("jeszcze puste", (Path(d) / "a.html").read_text(encoding="utf-8"))


class ScalanieDuplikatow(unittest.TestCase):
    def _w(self, i, title, **kw):
        w = {"id": f"i{i}", "title": title, "url": f"https://x.pl/{i}", "source": "A", "source_id": "a",
             "first_seen": "2026-10-20", "published": "2026-10-20", "kind": "inne", "place": "cała gmina",
             "when": None, "event_iso": None, "tkey": f"k{i}"}
        w.update(kw)
        return w

    def test_ten_sam_temat_w_jednym_zrodle_jest_scalany(self):
        a = self._w(1, "Projekt zakłada automatyczne odnawianie 800+")
        b = self._w(2, "800+ ma być odnawiane automatycznie", first_seen="2026-10-21")
        store = {"i1": a, "i2": b}
        self.assertEqual(scraper.scal_duplikaty(store), 1)
        self.assertEqual(list(store), ["i1"])

    def test_wydarzenia_z_roznymi_datami_zostaja_osobno(self):
        a = self._w(1, "Festiwal Nauki i Pasji – DZIEŃ EGIPTU", kind="wyd", event_iso="2026-10-25")
        b = self._w(2, "Festiwal Nauki i Pasji – DZIEŃ ARCHEOLOGII", kind="wyd", event_iso="2026-10-26")
        store = {"i1": a, "i2": b}
        self.assertEqual(scraper.scal_duplikaty(store), 0)

    def test_zdarzenia_policji_nie_sa_scalane(self):
        a = self._w(1, "Zdarzenie w gminie", neutral=True, kind="zdr")
        b = self._w(2, "Zdarzenie w gminie", neutral=True, kind="zdr")
        store = {"i1": a, "i2": b}
        self.assertEqual(scraper.scal_duplikaty(store), 0)


class TylkoZNotka(unittest.TestCase):
    def test_wpisy_bez_notki_sa_ukryte_tylko_reczne_zostaja(self):
        base = {"title": "T", "url": "https://x.pl/1", "source": "Z", "source_id": "z", "first_seen": "2026-10-20",
                "published": "2026-10-20", "place": "cała gmina", "when": None, "event_iso": None}
        z_notka = dict(base, id="1", kind="inne", text="Notka.")
        bez = dict(base, id="2", kind="inne")
        ostrz = dict(base, id="3", kind="ost", source_id="kryzysowe")
        reczny = dict(base, id="4", kind="wyd", manual=True)
        self.assertEqual([i["id"] for i in render.z_notka([z_notka, bez, ostrz, reczny])], ["1", "4"])

    def test_scalenie_przenosi_notke_ze_starszego_wpisu_bez_notki(self):
        a = {"id": "a", "title": "Umowa na oświetlenie i monitoring ulic Grodzisk", "source": "A", "source_id": "a",
             "first_seen": "2026-10-20", "kind": "inw"}
        b = dict(a, id="b", first_seen="2026-10-21", text="Notka.", opis_auto=True)
        store = {"a": a, "b": b}
        self.assertEqual(scraper.scal_duplikaty(store), 1)
        self.assertEqual(store["a"]["text"], "Notka.")


class TylkoLokalne(unittest.TestCase):
    def test_inny_region_w_tytule(self):
        self.assertTrue(redakcja.inny_region("Kolejny alert RCB dla woj. lubelskiego i podkarpackiego"))
        self.assertTrue(redakcja.inny_region("Powódź w województwie opolskim"))
        self.assertFalse(redakcja.inny_region("Nagroda Marszałka Województwa Mazowieckiego"))
        self.assertFalse(redakcja.inny_region("Remont ulicy w Grodzisku"))

    def test_z_notka_ukrywa_inne_regiony_i_poza_okolica(self):
        base = {"url": "https://x.pl/1", "source": "Z", "source_id": "twoje-miasto", "first_seen": "2026-10-20",
                "published": "2026-10-20", "place": "cała gmina", "when": None, "event_iso": None}
        rcb = dict(base, id="1", kind="ost", title="Alert RCB dla woj. lubelskiego", text="Notka o alercie.")
        poza = dict(base, id="2", kind="inne", title="Ceny paliw w kraju", text="Notka o cenach.", poza_okolica=True)
        ok = dict(base, id="3", kind="inne", title="Remont w Grodzisku", text="Notka o remoncie.")
        ost_portal = dict(base, id="4", kind="ost", title="Ostrzeżenie")          # z portalu ogólnego, bez notki
        ost_lokalne = dict(base, id="5", kind="ost", title="Ostrzeżenie", source_id="kryzysowe")
        self.assertEqual([i["id"] for i in render.z_notka([rcb, poza, ok, ost_portal, ost_lokalne])], ["3"])   # bez notki nic się nie pokazuje

    def test_portal_ogolny_wymaga_gminy_w_tytule_lub_tresci(self):
        base = {"url": "https://x.pl/1", "source": "Z", "source_id": "twoje-miasto", "first_seen": "2026-10-20",
                "published": "2026-10-20", "place": "Grodzisk Mazowiecki", "kind": "inne", "when": None, "event_iso": None}
        krajowy = dict(base, id="1", title="Kontrole placówek w całym kraju", text="Policja przeprowadziła kontrole w całym kraju.")
        cudzy = dict(base, id="2", title="Zawodnik klubu z Nowego Dworu piąty na ME", text="Reprezentant klubu zajął piąte miejsce.")
        lokalny = dict(base, id="3", title="Zmiany w ruchu", text="W Grodzisku Mazowieckim zmienia się organizacja ruchu.")
        lokalny_zrodlo = dict(base, id="4", source_id="policja", title="Policja ostrzega", text="Notka.")
        self.assertEqual([i["id"] for i in render.z_notka([krajowy, cudzy, lokalny, lokalny_zrodlo])], ["3", "4"])

    def test_dopisz_nie_zuzywa_limitu_na_portal_ogolny_bez_gminy(self):
        it = {"id": "1", "title": "Ceny paliw w kraju", "url": "https://x.pl/1", "source": "Z", "source_id": "twoje-miasto",
              "first_seen": TODAY.isoformat(), "published": TODAY.isoformat(), "kind": "inne", "place": "Grodzisk Mazowiecki"}
        class F:
            strony = {"https://x.pl/1": "<html><body><p>" + "Ceny paliw w całym kraju rosną. " * 20 + "</p></body></html>"}
        wywolania = []
        n = streszczenia.dopisz({"1": it}, {"twoje-miasto": {"streszczaj": True}}, F(), TODAY, 5,
                                llm=lambda t: wywolania.append(t) or "Notka.")
        self.assertEqual((n, wywolania), (0, []))
        self.assertTrue(it.get("poza_okolica"))

    def test_limit_liczy_zapytania_do_modelu_a_nie_odrzucone_wpisy(self):
        def wpis(n, zrodlo, tytul):
            return {"id": str(n), "title": tytul, "url": f"https://x.pl/{n}", "source": "Z", "source_id": zrodlo,
                    "first_seen": TODAY.isoformat(), "published": TODAY.isoformat(), "kind": "inne", "place": "Grodzisk Mazowiecki"}
        store = {str(n): wpis(n, "twoje-miasto", f"Ceny paliw w kraju {n}") for n in range(5)}
        store["9"] = wpis(9, "policja", "Policja w Grodzisku Mazowieckim zaprasza")
        class F:
            strony = {f"https://x.pl/{n}": "<html><body><p>" + "Ceny paliw w całym kraju rosną. " * 20 + "</p></body></html>" for n in range(5)}
            strony["https://x.pl/9"] = "<html><body><p>" + "Policja w Grodzisku Mazowieckim zaprasza na spotkanie z mieszkańcami. " * 10 + "</p></body></html>"
        zrodla = {"twoje-miasto": {"streszczaj": True}, "policja": {"streszczaj": True}}
        wywolania = []
        n = streszczenia.dopisz(store, zrodla, F(), TODAY, 2, llm=lambda t: wywolania.append(t) or "Policja zaprasza mieszkańców gminy na spotkanie informacyjne.")
        self.assertEqual((len(wywolania), n), (1, 1))      # 5 wpisów ogólnopolskich odpadło bez modelu i nie zjadło limitu 2

    def test_stary_wpis_z_przyszlym_terminem_dostaje_notke(self):
        it = {"id": "1", "title": "Stopnie alarmowe", "url": "https://x.pl/1", "source": "Z", "source_id": "z",
              "first_seen": TODAY.isoformat(), "published": "2026-01-01", "kind": "ost", "place": "cała gmina",
              "event_iso": (TODAY + timedelta(days=30)).isoformat()}
        self.assertEqual(len(streszczenia.kandydaci({"1": it}, {"z": {"streszczaj": True}}, TODAY)), 1)

    def test_model_odpowiada_poza_okolica(self):
        it = {"id": "1", "title": "Ceny paliw w kraju", "url": "https://x.pl/1", "source": "Z", "source_id": "z",
              "first_seen": TODAY.isoformat(), "published": TODAY.isoformat(), "kind": "inne", "place": "cała gmina"}
        store = {"1": it}
        class F:
            strony = {"https://x.pl/1": "<html><body><p>" + "Ceny paliw w całym kraju rosną. " * 20 + "</p></body></html>"}
        n = streszczenia.dopisz(store, {"z": {"streszczaj": True}}, F(), TODAY, 5, llm=lambda t: "POZA_OKOLICA")
        self.assertEqual(n, 0)
        self.assertTrue(it.get("poza_okolica"))
        self.assertNotIn("text", it)


class TylkoGminaGrodzisk(unittest.TestCase):
    def test_wpisy_spoza_gminy_sa_ukryte(self):
        base = {"url": "https://x.pl/1", "source": "Z", "source_id": "z", "first_seen": "2026-10-20",
                "published": "2026-10-20", "when": None, "event_iso": None, "kind": "inne", "title": "T", "text": "Notka."}
        ids = {m: dict(base, id=m, place=m) for m in ["Grodzisk Mazowiecki", "cała gmina", "Milanówek",
                                                       "Podkowa Leśna", "okolica"]}
        wynik = {i["id"] for i in render.z_notka(list(ids.values()))}
        self.assertEqual(wynik, {"Grodzisk Mazowiecki", "cała gmina"})


class TytulyAI(unittest.TestCase):
    ARTYKUL = Notki.ARTYKUL
    ZR = Notki.ZR
    NOTKA = "Od 27 października przebudowa wodociągu zamknie ulicę Kościuszki, objazd pójdzie Szkolną i Piękną."
    TYTUL = "Ulica Kościuszki zamknięta na czas prac przy wodociągu"

    def _store(self, **kw):
        it = {"id": "a", "title": "Zamknięcie ulicy Kościuszki", "url": "https://grodzisk.pl/a", "source": "Urząd Miejski",
              "source_id": "um", "first_seen": "2026-10-19", "published": "2026-10-19", "kind": "inw",
              "place": "Grodzisk Mazowiecki", "when": None, "event_iso": None}
        it.update(kw)
        return {"a": it}

    def test_rozbija_odpowiedz_w_dwoch_formatach(self):
        self.assertEqual(streszczenia.rozbij_odpowiedz(f"TYTUŁ: {self.TYTUL}\nNOTKA: {self.NOTKA}"), (self.TYTUL, self.NOTKA))
        self.assertEqual(streszczenia.rozbij_odpowiedz(f"**TYTUŁ:** {self.TYTUL}\n\n**NOTKA:** {self.NOTKA}"), (self.TYTUL, self.NOTKA))
        self.assertEqual(streszczenia.rozbij_odpowiedz(self.NOTKA), (None, self.NOTKA))      # stary format: sama notka
        self.assertEqual(streszczenia.rozbij_odpowiedz("POZA_OKOLICA"), (None, "POZA_OKOLICA"))

    def test_tytul_ai_przechodzi_kontrole(self):
        self.assertEqual(streszczenia.sprawdz_tytul(self.TYTUL + ".", "Zamknięcie ulicy Kościuszki", self.ARTYKUL), self.TYTUL)

    def test_odrzuca_zly_tytul(self):
        z = "Zamknięcie ulicy Kościuszki"
        zle = {"identyczny": z,
               "prawie ten sam": "Zamknięcie ulicy Kościuszki z powodu prac",
               "wykrzyknik": "Uwaga, ulica Kościuszki zamknięta na miesiąc!",
               "pytanie": "Czy ulica Kościuszki będzie zamknięta na miesiąc?",
               "urwany": "Ulica Kościuszki zostanie zamknięta z powodu prac w",
               "wymyślona liczba": "Ulica Kościuszki zamknięta na 45 dni z powodu wodociągu",
               "dane osoby": "Ranny 35-latek trafił do szpitala po wypadku na ulicy Kościuszki",
               "przepisany z artykułu": "Objazd wyznaczono ulicami Szkolną i Piękną, a prace potrwają",
               "za krótki": "Zamknięta ulica", "pusty": ""}
        for powod, t in zle.items():
            self.assertIsNone(streszczenia.sprawdz_tytul(t, z, self.ARTYKUL), powod)

    def test_notka_i_tytul_z_jednego_zapytania(self):
        store = self._store()
        zapytan = []
        def llm(t):
            zapytan.append(t)
            return f"TYTUŁ: {self.TYTUL}\nNOTKA: {self.NOTKA}"
        n = streszczenia.dopisz(store, self.ZR, Notki.F(f"<article>{self.ARTYKUL}</article>"), TODAY, 5, llm)
        self.assertEqual(n, 1)
        self.assertEqual(store["a"]["tytul"], self.TYTUL)
        self.assertEqual(store["a"]["title"], "Zamknięcie ulicy Kościuszki")      # oryginał zostaje do rozpoznawania powtórek
        self.assertEqual(len(zapytan), 1)

    def test_zly_tytul_nie_psuje_notki(self):
        store = self._store()
        llm = lambda t: f"TYTUŁ: Zamknięcie ulicy Kościuszki\nNOTKA: {self.NOTKA}"
        streszczenia.dopisz(store, self.ZR, Notki.F(f"<article>{self.ARTYKUL}</article>"), TODAY, 5, llm)
        self.assertIn("przebudowa wodociągu", store["a"]["text"])
        self.assertNotIn("tytul", store["a"])

    def test_zalegle_tytuly_dopisywane_z_notki(self):
        store = self._store(text=self.NOTKA, opis_auto=True)
        zapytan = []
        llm = lambda t: zapytan.append(t) or f"TYTUŁ: {self.TYTUL}\nNOTKA: {self.NOTKA}"
        self.assertEqual(streszczenia.dopisz_tytuly(store, TODAY, 5, llm), 1)
        self.assertEqual(store["a"]["tytul"], self.TYTUL)
        self.assertIn("Zamknięcie ulicy Kościuszki", zapytan[0])
        self.assertEqual(streszczenia.dopisz_tytuly(store, TODAY, 5, llm), 0)      # drugi raz nie pyta o ten sam wpis
        self.assertEqual(len(zapytan), 1)

    def test_zalegle_tytuly_pomijaja_zdarzenia_stare_i_juz_probowane(self):
        llm = lambda t: f"TYTUŁ: {self.TYTUL}\nNOTKA: {self.NOTKA}"
        for kw in ({"kind": "zdr"}, {"neutral": True}, {"published": "2026-09-01", "first_seen": "2026-09-01"}, {"tytul_proba": True}):
            self.assertEqual(streszczenia.dopisz_tytuly(self._store(text=self.NOTKA, **kw), TODAY, 5, llm), 0, kw)

    def test_zalegle_tytuly_koncza_na_limicie_zapytan(self):
        import urllib.error
        store = {str(i): dict(self._store(text=self.NOTKA)["a"], id=str(i), url=f"https://grodzisk.pl/{i}") for i in range(3)}
        wywolania = []
        def llm(t):
            wywolania.append(t)
            raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        self.assertEqual(streszczenia.dopisz_tytuly(store, TODAY, 5, llm), 0)
        self.assertEqual(len(wywolania), 1)
        self.assertFalse(any(i.get("tytul_proba") for i in store.values()))      # wpisy zostają do następnego przebiegu

    def test_strona_pokazuje_tytul_ai_a_bez_niego_oryginal(self):
        today = date(2026, 10, 19)
        base = {"url": "https://x.pl/1", "source": "Źródło", "source_id": "z1", "first_seen": "2026-10-19",
                "published": "2026-10-19", "kind": "inne", "place": "cała gmina", "when": None, "event_iso": None, "text": "Notka."}
        items = [dict(base, id="1", title="Oryginalny tytuł jeden", tytul="Własny tytuł AI numer jeden"),
                 dict(base, id="2", url="https://x.pl/2", title="Oryginalny tytuł dwa")]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "index.html"
            render.build(items, Path(__file__).resolve().parent / "template.html", out, today)
            page = out.read_text(encoding="utf-8")
        self.assertIn("Własny tytuł AI numer jeden", page)
        self.assertNotIn("Oryginalny tytuł jeden", page)
        self.assertIn("Oryginalny tytuł dwa", page)


class GodzinaAktualizacji(unittest.TestCase):
    def _strona(self, aktualizacja=None):
        item = {"id": "1", "title": "Tytuł", "url": "https://x.pl/1", "source": "Źródło", "source_id": "z1",
                "first_seen": "2026-10-22", "published": "2026-10-22", "kind": "inne", "place": "cała gmina",
                "when": None, "event_iso": None, "text": "Notka."}
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "index.html"
            render.build([item], Path(__file__).resolve().parent / "template.html", out, date(2026, 10, 22), aktualizacja)
            return out.read_text(encoding="utf-8")

    def test_aktualizacja_ma_date_i_godzine(self):
        page = self._strona(datetime(2026, 10, 22, 15, 7))
        self.assertIn("Ostatnia aktualizacja: 22.10.2026, godz. 15:07", page)

    def test_bez_czasu_jest_sama_data(self):
        page = self._strona()
        self.assertIn("Ostatnia aktualizacja: 22.10.2026 ·", page)

    def test_czas_z_utc_jest_pokazany_po_polsku(self):
        with tempfile.TemporaryDirectory() as d:
            status = Path(d) / "status.json"
            status.write_text('{"run": "2026-10-22T13:07:00"}', encoding="utf-8")      # stary zapis: czas serwera, czyli UTC
            with mock.patch.object(scraper, "STATUS", status):
                v = scraper.czas_ostatniego_przebiegu(None)
        self.assertEqual((v.hour, v.minute), (15, 7))                                  # w październiku Polska to UTC+2

    def test_brak_status_json_daje_czas_domyslny(self):
        with mock.patch.object(scraper, "STATUS", Path("/nie/ma/status.json")):
            self.assertEqual(scraper.czas_ostatniego_przebiegu("domyślny"), "domyślny")


class Grafiki(unittest.TestCase):
    def _wpis(self, **kw):
        base = {"id": "1", "title": "Tytuł", "url": "https://x.pl/1", "source": "Źródło", "source_id": "z1",
                "first_seen": "2026-10-22", "published": "2026-10-22", "kind": "inne", "place": "cała gmina",
                "when": None, "event_iso": None, "text": "Notka."}
        base.update(kw)
        return base

    def test_kazdy_temat_ma_grafike_w_sprite(self):
        s = grafiki.sprite()
        for nazwa in grafiki.OPISY:
            self.assertIn(f'id="ilu-{nazwa}"', s)
        for nazwa, _ in grafiki.TEMATY:
            self.assertIn(nazwa, grafiki.OPISY)
        for nazwa in grafiki.PO_RODZAJU.values():
            self.assertIn(nazwa, grafiki.OPISY)

    def test_sprite_jest_poprawnym_xml(self):
        import xml.etree.ElementTree as ET
        korzen = ET.fromstring(grafiki.sprite())
        symbole = [el for el in korzen.iter() if el.tag.endswith("symbol")]
        self.assertEqual(len(symbole), len(grafiki.OPISY))
        self.assertLess(len(grafiki.sprite()), 12000)

    def test_temat_z_tytulu_i_notki(self):
        przyklady = {
            "Zmiany w ruchu przy cmentarzu": "droga", "Przerwa w dostawie wody na ulicy Karliczka": "woda",
            "WKD zmienia rozkład jazdy": "pociag", "Policja szuka zaginionego mężczyzny": "bezpieczenstwo",
            "Bezpłatne badania mammograficzne": "zdrowie", "Zapisy do przedszkola": "szkola",
            "Mecz Bogorii z Grudziądzem": "sport", "Koncert w Mediatece": "kultura",
            "Zbiórka odzieży w gminie": "srodowisko", "Gmina ogłosiła przetarg na projekt parku": "inwestycje",
            "Sesja Rady Miejskiej": "urzad"}
        for tytul, oczekiwany in przyklady.items():
            self.assertEqual(grafiki.temat(self._wpis(title=tytul, text=None)), oczekiwany, tytul)

    def test_bez_slow_kluczowych_temat_zalezy_od_rodzaju(self):
        self.assertEqual(grafiki.temat(self._wpis(title="Coś ogólnego", text=None, kind="wyd")), "kultura")
        self.assertEqual(grafiki.temat(self._wpis(title="Coś ogólnego", text=None, kind="inne")), "ogolne")

    def test_parking_to_droga_a_nie_park(self):
        self.assertEqual(grafiki.temat(self._wpis(title="Nowy parking przy dworcu", text=None, kind="inne")), "pociag")
        self.assertEqual(grafiki.temat(self._wpis(title="Nowy parking przy szkole podstawowej", text=None)), "szkola")
        self.assertEqual(grafiki.temat(self._wpis(title="Nowy parking na osiedlu", text=None)), "droga")

    def test_karta_ma_grafike_a_zdjecie_zastepuje_ja_z_podpisem(self):
        bez = grafiki.ilustracja(self._wpis(kind="inw", title="Remont drogi"))
        self.assertIn('class="ilu k-inw"', bez)
        self.assertIn('<use href="#ilu-droga"/>', bez)
        z = grafiki.ilustracja(self._wpis(kind="inw", obraz="https://grodzisk.pl/foto.jpg", obraz_autor="Urząd Miejski"))
        self.assertIn('src="https://grodzisk.pl/foto.jpg"', z)
        self.assertIn('referrerpolicy="no-referrer"', z)
        self.assertIn("Fot.: Urząd Miejski", z)
        self.assertNotIn("<use", z)

    def test_obraz_tylko_z_https(self):
        self.assertIn("<use", grafiki.ilustracja(self._wpis(obraz="http://x.pl/a.jpg")))
        self.assertIn("<use", grafiki.ilustracja(self._wpis(obraz="javascript:alert(1)")))

    def test_strona_ma_sprite_i_grafiki_na_kartach_i_czolowce(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "index.html"
            render.build([self._wpis(kind="inw", title="Remont drogi")], Path(__file__).resolve().parent / "template.html", out, date(2026, 10, 22))
            page = out.read_text(encoding="utf-8")
        self.assertEqual(page.count('<symbol id="ilu-'), len(grafiki.OPISY))
        self.assertIn('class="hero-ilu"', page)
        self.assertIn('<div class="ilu k-inw"', page)
        self.assertIn("poglądowe", page)


class ZdjeciaCommons(unittest.TestCase):
    def _strona(self, tytul, mime="image/jpeg", szer=2000, licencja="CC BY-SA 4.0", **meta):
        m = {"LicenseShortName": {"value": licencja}, "Artist": {"value": '<a href="//x">Jan <b>Kowalski</b></a>'},
             "ImageDescription": {"value": "Stacja &amp; peron"}}
        m.update(meta)
        return {"title": tytul, "imageinfo": [{"mime": mime, "width": szer, "height": 1200, "url": "https://upload.wikimedia.org/a.jpg",
                                               "thumburl": "https://upload.wikimedia.org/t.jpg", "extmetadata": m}]}

    def test_licencje_wolne_tak_a_ograniczone_nie(self):
        for ok in ("CC BY-SA 4.0", "CC BY 3.0", "CC0", "Public domain", "CC-BY-SA-4.0", "PD-old"):
            self.assertTrue(zc.licencja_ok(ok), ok)
        for zle in ("CC BY-NC 4.0", "CC BY-ND 2.0", "CC BY-NC-SA 3.0", "", "Fair use", "All rights reserved", "GFDL"):
            self.assertFalse(zc.licencja_ok(zle), zle)

    def test_rekord_czysci_html_i_trzyma_autora_i_licencje(self):
        r = zc.rekord(self._strona("File:Stacja.jpg"))
        self.assertEqual(r["autor"], "Jan Kowalski")
        self.assertEqual(r["opis"], "Stacja & peron")
        self.assertEqual(r["licencja"], "CC BY-SA 4.0")
        self.assertTrue(r["strona"].startswith("https://commons.wikimedia.org/wiki/File%3AStacja.jpg") or "File:Stacja.jpg" in r["strona"])

    def test_rekord_odrzuca_zly_format_maly_rozmiar_i_licencje(self):
        self.assertIsNone(zc.rekord(self._strona("File:a.svg", mime="image/svg+xml")))
        self.assertIsNone(zc.rekord(self._strona("File:a.jpg", szer=640)))
        self.assertIsNone(zc.rekord(self._strona("File:a.jpg", licencja="CC BY-NC 4.0")))
        self.assertIsNone(zc.rekord({"title": "File:a.jpg"}))

    def test_uwagi_ostrzegaja_o_ludziach_i_ograniczeniach(self):
        r = zc.rekord(self._strona("File:a.jpg", ImageDescription={"value": "Portret burmistrza"}, Restrictions={"value": "trademarked"}))
        self.assertTrue(any("ludzie" in u for u in r["uwagi"]))
        self.assertTrue(any("trademarked" in u for u in r["uwagi"]))

    def _fetch(self, zapytania):
        def fetch(par):
            zapytania.append(par)
            if par.get("list") == "search":
                tytuly = {"Grodzisk Mazowiecki": ["Category:Grodzisk Mazowiecki", "Category:Grodzisk Wielkopolski"],
                          "Milanówek": ["Category:Milanówek"]}.get(par["srsearch"], [])
                return {"query": {"search": [{"title": t} for t in tytuly]}}
            if par.get("list") == "categorymembers":
                dane = {"Category:Grodzisk Mazowiecki": [{"title": "File:Stacja.jpg"}, {"title": "Category:Parki Grodziska Mazowieckiego"}],
                        "Category:Parki Grodziska Mazowieckiego": [{"title": "File:Park.jpg"}, {"title": "File:Stacja.jpg"}],
                        "Category:Milanówek": [{"title": "File:Maly.jpg"}]}
                return {"query": {"categorymembers": dane.get(par["cmtitle"], [])}}
            strony = {"File:Stacja.jpg": self._strona("File:Stacja.jpg"), "File:Park.jpg": self._strona("File:Park.jpg", licencja="CC0"),
                      "File:Maly.jpg": self._strona("File:Maly.jpg", szer=400)}
            return {"query": {"pages": [strony[t] for t in par["titles"].split("|")]}}
        return fetch

    def test_kategorie_tylko_pasujace_do_miejscowosci(self):
        kat = zc.znajdz_kategorie(self._fetch([]))
        self.assertEqual(kat, ["Category:Grodzisk Mazowiecki", "Category:Milanówek"])      # bez Grodziska Wielkopolskiego

    def test_zbieranie_schodzi_do_podkategorii_bez_powtorek(self):
        pliki = zc.zbierz_pliki(self._fetch([]), ["Category:Grodzisk Mazowiecki"])
        self.assertEqual(pliki, ["File:Stacja.jpg", "File:Park.jpg"])

    def test_calosc_zapisuje_json_i_arkusz(self):
        zapytania = []
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(zc.main(self._fetch(zapytania), Path(d)), 0)
            kand = json.loads((Path(d) / "zdjecia_kandydaci.json").read_text(encoding="utf-8"))
            arkusz = (Path(d) / "zdjecia_kandydaci.html").read_text(encoding="utf-8")
        self.assertEqual({k["tytul"] for k in kand}, {"File:Stacja.jpg", "File:Park.jpg"})      # mały plik odpadł
        self.assertIn("Kopiuj listę zaznaczonych", arkusz)
        self.assertIn("File:Park.jpg", arkusz)

    def test_brak_kategorii_to_blad_a_nie_pusty_plik(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(zc.main(lambda par: {}, Path(d)), 1)
            self.assertFalse((Path(d) / "zdjecia_kandydaci.json").exists())

    def test_arkusz_ucieka_html(self):
        k = zc.rekord(self._strona('File:"><script>x</script>.jpg'))
        self.assertNotIn("<script>x</script>", zc.arkusz([k]))


class TerminyIDuplikaty(unittest.TestCase):
    def _wpis(self, **kw):
        base = {"id": "1", "title": "Tytuł", "url": "https://x.pl/1", "source": "Źródło", "source_id": "z1",
                "first_seen": "2026-10-19", "published": "2026-10-19", "kind": "inne", "place": "cała gmina",
                "when": None, "event_iso": None, "text": "Notka."}
        base.update(kw)
        return base

    def test_data_bez_roku_sprzed_trzech_miesiecy_to_przeszlosc_a_nie_przyszly_rok(self):
        today = date(2026, 10, 22)
        self.assertEqual(wyciagnij_termin("Zapisy do 29.07", today)[1], "2026-07-29")
        self.assertEqual(wyciagnij_termin("Bal 14 stycznia", today)[1], "2027-01-14")

    def test_zbyt_odlegly_termin_jest_usuwany(self):
        store = {"a": self._wpis(id="a", kind="wyd", event_iso="2027-07-29", when="29.07.2027")}
        self.assertEqual(scraper.napraw_terminy(store, date(2026, 10, 22)), 1)
        self.assertIsNone(store["a"]["event_iso"])

    def test_wydarzenie_bez_terminu_dostaje_go_z_notki_i_znika_gdy_minelo(self):
        today = date(2026, 10, 22)
        store = {"a": self._wpis(id="a", kind="wyd", first_seen="2026-10-19", published="2026-10-19",
                                 text="Debata odbędzie się 9 października 2026 roku o godzinie 15:00.")}
        scraper.napraw_terminy(store, today)
        self.assertEqual(store["a"]["event_iso"], "2026-10-09")
        self.assertEqual(render.widoczne(list(store.values()), today), [])

    def test_wydarzenie_z_przyszlym_terminem_z_notki_zostaje(self):
        today = date(2026, 10, 22)
        store = {"a": self._wpis(id="a", kind="wyd", text="Spotkanie odbędzie się 27 października o godzinie 18:00.")}
        scraper.napraw_terminy(store, today)
        self.assertEqual(store["a"]["event_iso"], "2026-10-27")
        self.assertEqual(len(render.widoczne(list(store.values()), today)), 1)

    def test_ten_sam_temat_w_roznych_zrodlach_z_innymi_slowami_jest_scalany(self):
        a = self._wpis(id="a", source_id="um", title="Projekt planu ogólnego Gminy Grodzisk Mazowiecki")
        b = self._wpis(id="b", source_id="tm", title="Projekt planu ogólnego jest już dostępny")
        c = self._wpis(id="c", source_id="pr", title="Grodzisk Mazowiecki pokazał projekt planu ogólnego. Mieszkańcy będą mogli zgłaszać uwagi")
        self.assertTrue(scraper.ten_sam_temat(a, b))
        self.assertTrue(scraper.ten_sam_temat(a, c))

    def test_ogolne_slowa_urzedowe_nie_skleja_roznych_konsultacji(self):
        a = self._wpis(id="a", source_id="tm", title="Konsultacje programu współpracy na 2027 rok")
        b = self._wpis(id="b", source_id="ngo", title="Konsultacje projektu rocznego programu współpracy Województwa Mazowieckiego")
        self.assertFalse(scraper.ten_sam_temat(a, b))

    def test_luzna_regula_nie_laczy_wpisow_z_jednego_zrodla(self):
        a = self._wpis(id="a", source_id="g24", title="226 kilometrów sieci i dwa sposoby kanalizacji w gminie")
        b = self._wpis(id="b", source_id="g24", title="38 kilometrów sieci już działa. Kanalizacja ciśnieniowa bez tajemnic")
        self.assertFalse(scraper.ten_sam_temat(a, b))

    def _strona(self, items, today):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "index.html"
            render.build(items, Path(__file__).resolve().parent / "template.html", out, today)
            return out.read_text(encoding="utf-8")

    def test_blok_terminow_sortuje_po_dacie_i_pomija_przeszle_dalekie_i_zdarzenia(self):
        today = date(2026, 10, 22)
        items = [self._wpis(id="1", url="https://x.pl/1", kind="wyd", title="Koncert w sobotę", event_iso="2026-10-24", when="24.10, godz. 18:00"),
                 self._wpis(id="2", url="https://x.pl/2", kind="wyd", title="Spotkanie jutro", event_iso="2026-10-23", when="23.10, godz. 17:00"),
                 self._wpis(id="3", url="https://x.pl/3", kind="inne", title="Nabór wniosków do poniedziałku", event_iso="2026-10-26", when="26.10"),
                 self._wpis(id="4", url="https://x.pl/4", kind="wyd", title="Wydarzenie za miesiąc", event_iso="2026-11-30", when="30.11"),
                 self._wpis(id="5", url="https://x.pl/5", kind="zdr", neutral=True, title="Interwencja", event_iso="2026-10-23", when="23.10")]
        page = self._strona(items, today)
        blok = page[page.index('id="terminy"'):]
        blok = blok[:blok.index("</section>")]
        kolejnosc = [blok.index(t) for t in ("Spotkanie jutro", "Koncert w sobotę", "Nabór wniosków")]
        self.assertEqual(kolejnosc, sorted(kolejnosc))
        self.assertNotIn("Wydarzenie za miesiąc", blok)
        self.assertNotIn("Interwencja", blok)

    def test_bez_nadchodzacych_terminow_nie_ma_bloku(self):
        page = self._strona([self._wpis()], date(2026, 10, 22))
        self.assertNotIn('class="terminy"', page)

    def test_elementy_filtrowane_miejscowoscia_maja_miejsce_i_rodzaj(self):
        """Filtr miejscowości w przeglądarce pokazuje tylko wpisy o niej (z "cała gmina" zostają ostrzeżenia), więc
        każdy filtrowany element musi znać swoje miejsce i rodzaj."""
        today = date(2026, 10, 22)
        items = [self._wpis(id="1", url="https://x.pl/1", kind="wyd", place="Szczęsne", title="Piknik w Szczęsnem",
                            event_iso="2026-10-24", when="24.10")]
        page = self._strona(items, today)
        self.assertRegex(page, r'class="tick"[^>]*data-place="Szczęsne"[^>]*data-kind="wyd"')
        self.assertRegex(page, r'class="termin" data-place="Szczęsne" data-kind="wyd"')
        self.assertIn('c.dataset.kind === "ost"', page)

    def test_plakietka_miejsca_w_terminach_tylko_dla_innych_miejscowosci_niz_miasto(self):
        today = date(2026, 10, 22)
        items = [self._wpis(id="1", url="https://x.pl/1", kind="wyd", place="Grodzisk Mazowiecki", title="Koncert w mieście",
                            event_iso="2026-10-24", when="24.10"),
                 self._wpis(id="2", url="https://x.pl/2", kind="wyd", place="Szczęsne", title="Piknik na wsi",
                            event_iso="2026-10-25", when="25.10")]
        page = self._strona(items, today)
        blok = page[page.index('id="terminy"'):]
        blok = blok[:blok.index("</section>")]
        wiersze = blok.split('<li class="termin"')[1:]
        self.assertNotIn('class="badge"', wiersze[0])      # miasto: bez plakietki
        self.assertIn('<span class="badge">Szczęsne</span>', wiersze[1])

    def test_blok_terminow_ma_limit(self):
        today = date(2026, 10, 22)
        items = [self._wpis(id=str(n), url=f"https://x.pl/{n}", kind="wyd", title=f"Wydarzenie numer {n}",
                            event_iso="2026-10-25", when="25.10") for n in range(render.TERMINY_MAX + 4)]
        page = self._strona(items, today)
        blok = page[page.index('id="terminy"'):]
        self.assertEqual(blok[:blok.index("</section>")].count('class="termin"'), render.TERMINY_MAX)
