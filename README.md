# Grodzisk lokalnie: bot i strona

Bot raz dziennie zbiera tytuły, daty i linki z lokalnych źródeł (`sources.json`), klasyfikuje je
(rodzaj, miejscowość, termin) i buduje `index.html`. Hostuje to GitHub Pages.

## Pliki
- `sources.json`: lista źródeł (włączanie i wyłączanie: pole `enabled`, rytm: `daily`, `weekly`, `rare`)
- `scraper.py`: pobieranie, zapis do `data/items.json`, wywołanie generatora strony
- `klasyfikacja.py`: reguły rodzaju, miejscowości i terminu
- `render.py` + `template.html`: wygląd strony
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
