import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
import urllib.error
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

    def _it(self, **kw):
        base = {"id": "1", "title": "Tytuł", "url": "https://x.pl/1", "source": "Źródło", "first_seen": "2026-10-19",
                "published": "2026-10-19", "kind": "inne", "place": "cała gmina", "when": None, "event_iso": None}
        base.update(kw)
        return base

    def test_zdarzenie_ma_opis_bez_szczegolow_i_nie_jest_jedynka(self):
        page = self._strona([self._it(kind="zdr", title="Wypadek drogowy: Kozerki", place="Kozerki", neutral=True)])
        self.assertIn("Sprawę opisuje Źródło", page)
        self.assertNotIn("hero-tile\"", page)

    def test_jedynka_dnia_woli_gmine_od_okolicy(self):
        milanowek = self._it(id="m", url="https://x.pl/m", kind="ost", place="Milanówek", title="Ostrzeżenie w Milanówku")
        gmina = self._it(id="g", url="https://x.pl/g", kind="inw", place="Natolin", title="Remont drogi w Natolinie")
        page = self._strona([milanowek, gmina])
        self.assertLess(page.index("Remont drogi w Natolinie"), page.index("Ostrzeżenie w Milanówku"))

    def test_brak_podwojnej_kropki_po_skrocie_zrodla(self):
        it = self._it(kind="zdr", neutral=True, source="KPP Grodzisk Maz.")
        self.assertEqual(redakcja.opis(it, TODAY), "Sprawę opisuje KPP Grodzisk Maz. Szczegóły pod linkiem do źródła.")

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
        self.assertIn("zauważono", page)
        self.assertNotIn("dzisiaj", page.split("<main>")[1].split("<script>")[0])

    def test_zapowiedzi_bez_terminu_sa_ograniczone(self):
        items = [self._it(id=str(i), url=f"https://x.pl/{i}", kind="wyd", title=f"Zapowiedź {i}") for i in range(6)]
        items.append(self._it(id="stara", url="https://x.pl/s", kind="wyd", title="Stara zapowiedź",
                              first_seen="2026-10-10", published=None))
        page = self._strona(items)
        self.assertEqual(page.count('<article class="portal-card'), render.BEZ_TERMINU_MAX)
        self.assertNotIn("Stara zapowiedź", page)

    def test_wpis_reczny_pokazuje_wlasny_opis_i_ikone(self):
        page = self._strona([self._it(kind="inw", text="Zamknięta ulica Kościuszki do piątku.", manual=True)])
        self.assertIn("Zamknięta ulica Kościuszki do piątku.", page)
        self.assertIn('<svg class="ico"', page)


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
        self.assertEqual(streszczenia.dopisz(store, self.ZR, f, TODAY, 5, llm), 0)
        self.assertEqual(f.wywolania, 1)                       # po pierwszym 429 koniec
        self.assertFalse(any(i.get("opis_proba") for i in store.values()))  # nic nie oznaczone, więc kolejny przebieg spróbuje znów

    def test_karta_oznacza_opis_automatyczny(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "index.html"
            it = {"id": "1", "title": "Tytuł", "url": "https://x.pl/1", "source": "Źródło", "first_seen": "2026-10-19",
                  "published": "2026-10-19", "kind": "inw", "place": "Natolin", "when": None, "event_iso": None,
                  "text": "Od 27 października zamknięta zostanie ulica Kościuszki.", "opis_auto": True}
            render.build([it], Path(__file__).resolve().parent / "template.html", out, TODAY)
            page = out.read_text(encoding="utf-8")
        self.assertIn("ulica Kościuszki.", page)
        self.assertIn("Opis automatyczny.", page)

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
        streszczenia._gemini_ok.clear()
        try:
            self.assertEqual(streszczenia.wywolaj_gemini("t", "klucz"), "Notka z Gemini.")
            self.assertEqual(adresy, ["gemini-2.5-flash:generateContent", "gemini-2.5-flash-lite:generateContent"])
            streszczenia.wywolaj_gemini("t", "klucz")
            self.assertEqual(adresy[-1], "gemini-2.5-flash-lite:generateContent")   # od razu działający model
            self.assertEqual(len(adresy), 3)
        finally:
            streszczenia._otworz = stare
            streszczenia._gemini_ok.clear()

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
