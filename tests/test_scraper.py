import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import render
import scraper
from klasyfikacja import klasyfikuj_rodzaj, wyciagnij_termin, znajdz_miejsca

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
        self.assertEqual(klasyfikuj_rodzaj("Nowa dyrektor szkoły", hint="inw"), "inw")
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
            render.build(items, Path(__file__).resolve().parent.parent / "template.html", out, TODAY)
            page = out.read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("Wczorajszy koncert", page)
        self.assertIn("Kiedy: 25.10", page)
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


if __name__ == "__main__":
    unittest.main()
