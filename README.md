# Grodzisk lokalnie: bot i strona

Bot raz dziennie zbiera tytuły, daty i linki z lokalnych źródeł (`sources.json`), klasyfikuje je
(rodzaj, miejscowość, termin) i buduje `index.html`. Hostuje to GitHub Pages.

## Pliki
- `sources.json`: lista źródeł (włączanie i wyłączanie: pole `enabled`, rytm: `daily`, `weekly`, `rare`)
- `scraper.py`: pobieranie, zapis do `data/items.json`, wywołanie generatora strony
- `klasyfikacja.py`: reguły rodzaju, miejscowości i terminu
- `render.py` + `template.html`: wygląd strony (ikony rodzajów, daty po polsku, filtry)
- `redakcja.py`: zasady redakcyjne w kodzie (neutralne tytuły zdarzeń, daty, opisy, powtórki tematów)
- `reczne.py` + `data/manual.json`: wpisy ręczne (np. z Facebooka), sprawdzane przed publikacją
- `tests/`: testy (uruchamiają się przed każdym przebiegiem bota)
- `data/status.json`: wynik ostatniego przebiegu dla każdego źródła, tu szukaj błędów

## Ustawienia
W repozytorium: Settings → Secrets and variables → Actions → Variables → dodaj `BOT_CONTACT`
(Twój e-mail lub adres strony). Trafia do nagłówka User-Agent, żeby administratorzy stron wiedzieli, kto pobiera.

## Lokalnie
    pip install -r requirements.txt
    python -m unittest discover -s tests -v
    python scraper.py --all            # wszystkie włączone źródła
    python scraper.py --only mediateka # jedno źródło
    python scraper.py --render-only    # tylko przebuduj stronę z zapisanych danych

## Zasady
Zapisujemy tytuł, link, datę i fakty (rodzaj, miejscowość, termin). Nie kopiujemy zajawek ani treści
artykułów. Źródła z zastrzeżonymi prawami (np. GrodziskNews) są wyłączone do czasu uzyskania zgody.

## Wpisy ręczne (data/manual.json)
Plik to lista wpisów w nawiasach `[ ... ]`. Nowy wpis dopisujesz przed ostatnim `]`, a poprzedni kończysz przecinkiem.

    {"kind": "wydarzenie", "place": "Książenice", "date": "2026-10-25", "time": "18:00",
     "title": "Koncert w świetlicy", "text": "Wstęp wolny.", "url": "https://www.facebook.com/...", "source": "Facebook"}

Wymagane: `kind` (ostrzezenie, zdarzenie, wydarzenie, inwestycja, sport, wiadomosc), `place`, `date`, `title`, `url`.
Opcjonalne: `time` (tylko wydarzenia), `text` (do 300 znaków, własnymi słowami), `source`.
Po zapisaniu pliku na GitHubie strona przebudowuje się sama. Błąd w pliku (zła miejscowość, data, brak przecinka)
kończy przebieg na czerwono z komunikatem w logu, a opublikowana strona zostaje bez zmian.

## Zasady dotyczące zdarzeń
Tytuły zdarzeń są zastępowane neutralnymi (rodzaj zdarzenia i miejsce). Oryginalny tytuł nie jest zapisywany.
Wpisy ręczne o zdarzeniach z wiekiem lub stanem zdrowia osób są odrzucane.

## Notki pod tytułami (opcjonalne)
Gdy w Settings → Secrets and variables → Actions → **Secrets** jest `ANTHROPIC_API_KEY`, bot pisze 1-2 zdania pod tytułem
własnymi słowami (maks. 30 notek na przebieg, tylko wpisy z ostatnich 7 dni). Dotyczy tylko źródeł z `"streszczaj": true`
w `sources.json` (domyślnie instytucje publiczne), nigdy zdarzeń. Notka jest odrzucana, gdy zawiera dane osób albo
7 kolejnych słów z artykułu. Karta oznacza ją jako automatyczną. Model można zmienić zmienną `SUMMARY_MODEL`.
Bez klucza ten etap jest pomijany, a strona działa jak dotąd.
