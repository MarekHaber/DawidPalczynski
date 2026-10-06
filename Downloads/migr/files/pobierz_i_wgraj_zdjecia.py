"""
SKRYPT ZDJĘĆ: pobranie z Joomli (stara strona) -> wgranie do WordPress + podpięcie do artykułu
=================================================================================================

Co robi ten skrypt, krok po kroku, dla KAŻDEGO artykułu:
1. Sprawdza czy artykuł ma w ogóle zdjęcie główne (nie wszystkie mają)
2. Sprawdza we własnej mapie (mapa_zdjec.json) czy to zdjęcie już kiedyś wgraliśmy
   - jeśli tak: pomija pobieranie/wgrywanie, tylko upewnia się że jest podpięte do artykułu
   - jeśli nie: pobiera plik, wgrywa do WP, zapisuje w mapie
3. Ustawia wgrane zdjęcie jako "obrazek wyróżniający" (featured image) danego artykułu w WP

WAŻNE - kolejność uruchamiania skryptów:
Ten skrypt wymaga, żeby artykuły były JUŻ zaimportowane przez import_do_wordpress.py
(korzysta z pliku mapa_id.json, żeby wiedzieć który joomla_id odpowiada któremu
wpisowi w WordPressie).

Zanim odpalisz:
- Sprawdź czy stara.wroclawskakomunikacja.pl w ogóle działa (wpisz adres w przeglądarce)
  - jeśli strona pokazuje błąd 500 / nie działa, ten skrypt też nie zadziała,
    bo nie ma skąd pobrać zdjęć - poczekaj aż strona wróci
- Uzupełnij dane w sekcji KONFIGURACJA poniżej (te same co w import_do_wordpress.py)
"""

import json
import os
import time
import mimetypes
import requests

# ============================================================
# KONFIGURACJA
# ============================================================

WP_URL = "https://nowa.wroclawskakomunikacja.pl"   # Twój adres WordPressa
WP_USER = os.environ.get("WP_USER", "admin")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "")  # ustaw przed uruchomieniem: export WP_APP_PASSWORD="..."

ADRES_STAREJ_STRONY = "https://stara.wroclawskakomunikacja.pl"  # skąd pobieramy zdjęcia

PLIK_ARTYKULOW = "artykuly_przetworzone.json"
PLIK_MAPY_ID_ARTYKULOW = "mapa_id.json"       # joomla_id -> id wpisu w WP (z import_do_wordpress.py)
PLIK_MAPY_ZDJEC = "mapa_zdjec.json"           # ścieżka_zdjecia -> id zdjęcia w bibliotece mediów WP

AUTH = (WP_USER, WP_APP_PASSWORD)


# ============================================================
# FUNKCJE POMOCNICZE - obsługa lokalnych map (ten sam wzorzec co w imporcie artykułów)
# ============================================================

def wczytaj_json(sciezka, domyslna_wartosc):
    """Wczytuje plik JSON, a jeśli nie istnieje - zwraca podaną wartość domyślną."""
    if not os.path.exists(sciezka):
        return domyslna_wartosc
    with open(sciezka, "r", encoding="utf-8") as plik:
        return json.load(plik)


def zapisz_json(sciezka, dane):
    """Zapisuje dane do pliku JSON - wywołujemy po każdej udanej operacji,
    żeby nic nie zgubić w razie przerwania skryptu w połowie."""
    with open(sciezka, "w", encoding="utf-8") as plik:
        json.dump(dane, plik, ensure_ascii=False, indent=2)


# ============================================================
# GŁÓWNA LOGIKA
# ============================================================

def pobierz_zdjecie(sciezka_wzgledna):
    """
    Pobiera plik zdjęcia ze starej strony Joomla.
    sciezka_wzgledna - zwykle np. "images/zdjecia_do_wiadomosci/wiad_1619.jpg",
    ale w kilku przypadkach w Joomli ktoś ręcznie wpisał PEŁNY adres
    (np. "http://wroclawskakomunikacja.pl/images/...") zamiast ścieżki względnej -
    trzeba to rozpoznać, żeby nie skleić dwóch adresów w jeden (co dawało 404).

    Zwraca surowe bajty pliku (dane_pliku) i nazwę pliku, albo (None, None) przy błędzie.
    """
    if sciezka_wzgledna.startswith(("http://", "https://")):
        # To już jest pełny adres - tylko normalizujemy na https, bez doklejania czegokolwiek
        url = sciezka_wzgledna.replace("http://", "https://", 1)
    else:
        url = f"{ADRES_STAREJ_STRONY}/{sciezka_wzgledna.lstrip('/')}"

    try:
        odpowiedz = requests.get(url, timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"    [BŁĄD] Nie udało się połączyć: {e}")
        return None, None

    if odpowiedz.status_code != 200:
        print(f"    [BŁĄD] Nie udało się pobrać zdjęcia ({odpowiedz.status_code}): {url}")
        return None, None

    nazwa_pliku = os.path.basename(sciezka_wzgledna)
    return odpowiedz.content, nazwa_pliku


def wgraj_zdjecie_do_wp(dane_pliku, nazwa_pliku, opis_alt="", podpis=""):
    """
    Wysyła plik do biblioteki mediów WordPressa.
    Zwraca ID nowo utworzonego zdjęcia w WP, albo None przy błędzie.

    UWAGA: to jest inny sposób wysyłania niż zwykłe posty - zamiast JSON-a
    wysyłamy surowe bajty pliku, z nagłówkiem Content-Disposition (nazwa pliku)
    i Content-Type (typ pliku, np. image/jpeg).
    """
    typ_mime, _ = mimetypes.guess_type(nazwa_pliku)
    if typ_mime is None:
        typ_mime = "image/jpeg"  # rozsądna wartość domyślna

    naglowki = {
        "Content-Disposition": f'attachment; filename="{nazwa_pliku}"',
        "Content-Type": typ_mime,
    }

    url = f"{WP_URL}/wp-json/wp/v2/media"

    # Ponawiamy do 3 razy - serwer przy większym obciążeniu potrafi zwrócić
    # 504 Gateway Timeout (widzieliśmy to przy imporcie pojazdów). Bez ponawiania
    # takie chwilowe potknięcie oznaczałoby utratę zdjęcia w tym przebiegu.
    odpowiedz = None
    for proba in range(1, 4):
        try:
            odpowiedz = requests.post(url, headers=naglowki, data=dane_pliku, auth=AUTH, timeout=120)
        except requests.exceptions.RequestException as e:
            print(f"    [PRÓBA {proba}/3] błąd połączenia przy wgrywaniu: {e}")
            time.sleep(3)
            continue

        if odpowiedz.status_code in (200, 201):
            break

        print(f"    [PRÓBA {proba}/3] serwer zwrócił {odpowiedz.status_code} przy wgrywaniu zdjęcia")
        time.sleep(3)

    if odpowiedz is None or odpowiedz.status_code not in (200, 201):
        tresc_bledu = odpowiedz.text[:300] if odpowiedz is not None else "brak odpowiedzi"
        print(f"    [BŁĄD] Nie udało się wgrać zdjęcia do WP po 3 próbach: {tresc_bledu}")
        return None

    id_zdjecia = odpowiedz.json()["id"]

    # Drugi krok: uzupełniamy tekst alternatywny i podpis (osobne zapytanie,
    # bo WP nie pozwala ustawić alt_text w tym samym żądaniu co upload pliku)
    if opis_alt or podpis:
        dane_do_aktualizacji = {}
        if opis_alt:
            dane_do_aktualizacji["alt_text"] = opis_alt
        if podpis:
            dane_do_aktualizacji["caption"] = podpis  # tu ląduje np. "© Łukasz Kuczewski"

        url_aktualizacji = f"{WP_URL}/wp-json/wp/v2/media/{id_zdjecia}"
        requests.post(url_aktualizacji, json=dane_do_aktualizacji, auth=AUTH)

    return id_zdjecia


def ustaw_obrazek_wyrozniajacy(id_wpisu, id_zdjecia):
    """
    Ustawia dane zdjęcie jako "featured image" (obrazek wyróżniający) danego wpisu.
    """
    url = f"{WP_URL}/wp-json/wp/v2/posts/{id_wpisu}"
    odpowiedz = requests.post(url, json={"featured_media": id_zdjecia}, auth=AUTH)
    return odpowiedz.status_code in (200, 201)


def main():
    artykuly = wczytaj_json(PLIK_ARTYKULOW, [])
    # UWAGA: klucze w mapa_id.json mają teraz format "typ_joomlaID" (np. "artykul_1994",
    # "pojazd_58"), bo artykuły i pojazdy pochodzą z tej samej tabeli Joomli i mają
    # te same numery ID. Tutaj interesują nas TYLKO artykuły, więc bierzemy klucze
    # zaczynające się od "artykul_" i wyciągamy z nich sam numer.
    # (Stary format - sam numer bez prefiksu - też obsługujemy, dla bezpieczeństwa.)
    mapa_id_artykulow = {}
    for klucz, wartosc in wczytaj_json(PLIK_MAPY_ID_ARTYKULOW, {}).items():
        if klucz.startswith("artykul_"):
            mapa_id_artykulow[int(klucz.removeprefix("artykul_"))] = wartosc
        elif klucz.isdigit():
            mapa_id_artykulow[int(klucz)] = wartosc
        # klucze "pojazd_*" pomijamy - zdjęcia pojazdów to osobny temat
    mapa_zdjec = wczytaj_json(PLIK_MAPY_ZDJEC, {})

    print(f"Wczytano {len(artykuly)} artykułów")
    print(f"Wczytano mapę {len(mapa_id_artykulow)} zaimportowanych wcześniej artykułów")
    print(f"Wczytano mapę {len(mapa_zdjec)} już wgranych wcześniej zdjęć\n")

    licznik_wgranych = 0
    licznik_pominietych_brak_zdjecia = 0
    licznik_bledow = 0

    for numer, artykul in enumerate(artykuly, start=1):
        joomla_id = artykul["joomla_id"]
        sciezka_zdjecia = artykul.get("obrazek_glowny")

        # Pomijamy artykuły bez zdjęcia głównego
        if not sciezka_zdjecia:
            licznik_pominietych_brak_zdjecia += 1
            continue

        # Musimy wiedzieć, do którego wpisu w WP podpiąć to zdjęcie
        id_wpisu_w_wp = mapa_id_artykulow.get(joomla_id)
        if not id_wpisu_w_wp:
            print(f"[{numer}/{len(artykuly)}] [POMINIĘTO] Artykuł joomla_id={joomla_id} "
                  f"nie jest jeszcze zaimportowany do WP - najpierw odpal import_do_wordpress.py")
            continue

        print(f"[{numer}/{len(artykuly)}] {artykul['tytul']} (joomla_id={joomla_id})")

        # Sprawdzamy czy to zdjęcie już kiedyś wgraliśmy
        if sciezka_zdjecia in mapa_zdjec:
            id_zdjecia = mapa_zdjec[sciezka_zdjecia]
            print(f"    Zdjęcie już wgrane wcześniej (WP media ID={id_zdjecia}) - tylko podpinam")
        else:
            print(f"    Pobieram zdjęcie: {sciezka_zdjecia}")
            dane_pliku, nazwa_pliku = pobierz_zdjecie(sciezka_zdjecia)

            if dane_pliku is None:
                licznik_bledow += 1
                continue

            id_zdjecia = wgraj_zdjecie_do_wp(
                dane_pliku,
                nazwa_pliku,
                opis_alt=artykul.get("obrazek_alt", ""),
                podpis=artykul.get("obrazek_podpis_autor", ""),
            )

            if id_zdjecia is None:
                licznik_bledow += 1
                continue

            mapa_zdjec[sciezka_zdjecia] = id_zdjecia
            zapisz_json(PLIK_MAPY_ZDJEC, mapa_zdjec)  # zapisujemy od razu, na wypadek przerwania
            print(f"    [OK] Wgrano nowe zdjęcie (WP media ID={id_zdjecia})")

        # Podpinamy zdjęcie do artykułu jako obrazek wyróżniający
        if ustaw_obrazek_wyrozniajacy(id_wpisu_w_wp, id_zdjecia):
            licznik_wgranych += 1
        else:
            print(f"    [BŁĄD] Nie udało się podpiąć zdjęcia do artykułu")
            licznik_bledow += 1

        print()

    print("=" * 60)
    print(f"Gotowe! Podsumowanie:")
    print(f"  Zdjęcia podpięte poprawnie: {licznik_wgranych}")
    print(f"  Artykuły bez zdjęcia głównego (pominięte): {licznik_pominietych_brak_zdjecia}")
    print(f"  Błędy: {licznik_bledow}")


if __name__ == "__main__":
    main()
