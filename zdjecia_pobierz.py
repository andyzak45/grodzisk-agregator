"""Pobiera wybrane zdjęcia z Wikimedia Commons do repozytorium.

Wejście:  data/zdjecia_wybor.txt  (jeden tytuł pliku Commons na linię, np. "File:Stawy Goliana 2022.jpg")
Wyjście:  zdjecia/*.jpg|png       (zdjęcia zmniejszone przez Commons do ok. 1000 px szerokości)
          data/zdjecia.json       (autor, licencja, adres strony na Commons, miejscowość i temat każdego zdjęcia)
Licencję i autora sprawdzamy tu jeszcze raz, więc plik z niedozwoloną licencją nie trafi na stronę, nawet jeśli jest na liście.
Użycie: python zdjecia_pobierz.py
"""
import json
import re
import sys
import urllib.error
import urllib.request
import zlib
from pathlib import Path

import zdjecia_commons as zc
from grafiki import OPISY
from klasyfikacja import CALA_GMINA, norm, znajdz_miejsca

ROOT = Path(__file__).resolve().parent
SZEROKOSC = 1000
SZEROKOSC_ZAPASOWA = 700   # gdy miniatura 1000 px jest za ciężka (np. zdjęcie z dużą ilością detali), próbujemy mniejszej
MAX_BAJTOW = 800_000
TOWN = "Grodzisk Mazowiecki"
# kolejność ma znaczenie: pierwszy pasujący temat wygrywa (nazwy tematów jak w grafiki.py)
TEMATY = [("pociag", r"wkd|stacj|peron|przystan|rozjazd|kolej"), ("urzad", r"urzad|siedziba powiatu"),
          ("szkola", r"szkol|przedszkol"), ("sport", r"stadion|sportow|plac zabaw"),
          ("srodowisko", r"staw|\bpark\b"), ("kultura", r"kosciol|galeria|palacyk|willa|villa|dwor|pomnik|radiostacj"),
          ("droga", r"rondo|wiadukt|\bul\.|ulica")]


def nazwa(tytul):
    return re.sub(r"\.[A-Za-z]{3,4}$", "", tytul.removeprefix("File:"))


def temat(tytul):
    t = norm(nazwa(tytul))
    return next((k for k, wz in TEMATY if re.search(wz, t)), "ogolne")


def miejsce(tytul):
    """Miejscowość z nazwy pliku (słownik jak na stronie); bez nazwy w pliku to miasto, bo cała lista dotyczy Grodziska."""
    m = znajdz_miejsca(nazwa(tytul), default=CALA_GMINA)
    return TOWN if m == CALA_GMINA else m.split("|")[0]


def plik_lokalny(tytul, mime):
    slug = re.sub(r"[^a-z0-9]+", "-", norm(nazwa(tytul))).strip("-")[:50]
    return f"{slug}-{zlib.crc32(tytul.encode()) & 0xffff:04x}." + ("png" if mime == "image/png" else "jpg")


def pobierz_plik(url):
    req = urllib.request.Request(url, headers={"User-Agent": zc.USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(MAX_BAJTOW + 1)


def mniejsza_miniatura(fetch, tytul):
    d = fetch({"action": "query", "prop": "imageinfo", "titles": tytul, "iiprop": "url", "iiurlwidth": str(SZEROKOSC_ZAPASOWA)})
    for s in (d.get("query") or {}).get("pages", []):
        info = (s.get("imageinfo") or [None])[0]
        if info:
            return info.get("thumburl")
    return None


def wczytaj_wybor(sciezka):
    """Lista (tytuł, temat lub None). Linia "File:X.jpg | droga" to zdjęcie ogólne do tematu, bez miejscowości."""
    if not sciezka.exists():
        return []
    out, widziane = [], set()
    for linia in sciezka.read_text(encoding="utf-8").splitlines():
        tytul, _, t = (x.strip() for x in linia.partition("|"))
        if tytul.startswith("File:") and tytul not in widziane:
            widziane.add(tytul)
            out.append((tytul, t if t in OPISY else None))
    return out


def main(fetch=zc.pobierz, pobierz=pobierz_plik, katalog=ROOT):
    wybor = wczytaj_wybor(katalog / "data" / "zdjecia_wybor.txt")
    tematy_wyboru = dict(wybor)
    tytuly = [t for t, _ in wybor]
    if not tytuly:
        print("Brak tytułów w data/zdjecia_wybor.txt.")
        return 1
    (katalog / "zdjecia").mkdir(exist_ok=True)
    wynik, odpadly = [], []
    for i in range(0, len(tytuly), 40):
        paczka = tytuly[i:i + 40]
        d = fetch({"action": "query", "prop": "imageinfo", "titles": "|".join(paczka), "iiprop": "url|size|mime|extmetadata",
                   "iiurlwidth": str(SZEROKOSC)})
        znalezione = {s["title"]: s for s in (d.get("query") or {}).get("pages", [])}
        for t in paczka:
            s = znalezione.get(t)
            r = zc.rekord(s) if s and not s.get("missing") else None
            if not r:
                odpadly.append(t)
                continue
            lokalny = plik_lokalny(r["tytul"], (s["imageinfo"][0]).get("mime"))
            sciezka = katalog / "zdjecia" / lokalny
            if not sciezka.exists():
                try:
                    dane = pobierz(r["miniatura"])
                except (urllib.error.URLError, TimeoutError) as e:
                    print(f"  nie pobrano {t}: {type(e).__name__}")
                    odpadly.append(t)
                    continue
                if len(dane) > MAX_BAJTOW:
                    mala = mniejsza_miniatura(fetch, t)
                    if mala and mala != r["miniatura"]:
                        try:
                            dane = pobierz(mala)
                        except (urllib.error.URLError, TimeoutError):
                            pass
                if len(dane) > MAX_BAJTOW:
                    print(f"  pominięto {t}: plik większy niż {MAX_BAJTOW // 1000} KB")
                    odpadly.append(t)
                    continue
                sciezka.write_bytes(dane)
            wynik.append({"plik": f"zdjecia/{lokalny}", "tytul": r["tytul"], "strona": r["strona"], "autor": r["autor"],
                          "licencja": r["licencja"], "licencja_url": r["licencja_url"],
                          "miejsce": "" if tematy_wyboru.get(t) else miejsce(r["tytul"]),
                          "temat": tematy_wyboru.get(t) or temat(r["tytul"])})
    (katalog / "data" / "zdjecia.json").write_text(json.dumps(wynik, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Zdjęć gotowych: {len(wynik)}; odrzuconych lub nieznalezionych: {len(odpadly)}")
    for t in odpadly[:15]:
        print(f"  - {t}")
    return 0 if wynik else 1


if __name__ == "__main__":
    sys.exit(main())
