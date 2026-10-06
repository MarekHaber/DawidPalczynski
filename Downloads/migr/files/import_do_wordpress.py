"""
SKRYPT IMPORTU: Joomla (JSON) -> WordPress (REST API)
======================================================

Co robi ten skrypt, krok po kroku:
1. Wczytuje dane z pliku JSON (wyeksportowane przez Osobę 1 z Joomli)
2. Dla każdego rekordu sprawdza we WŁASNYM PLIKU "mapa_id.json" (nie w WP!)
   czy ten rekord już był kiedyś zaimportowany
   (żeby nie tworzyć duplikatów, gdy odpalimy skrypt kilka razy)
3. Jeśli nie ma go w mapie -> tworzy nowy wpis (POST) i zapisuje jego ID do mapy
   Jeśli już jest w mapie -> aktualizuje ten konkretny wpis (PUT)

WAŻNA UWAGA (dla zrozumienia, dlaczego działa właśnie tak):
Standardowe REST API WordPressa NIE obsługuje wyszukiwania wpisów po polu meta
(np. "znajdź wpis, gdzie _joomla_id = 123"). Próba filtrowania po meta_key/meta_value
jest po cichu ignorowana przez WordPressa i zwraca po prostu pierwszy wpis z listy -
to prowadziło do BŁĘDU, w którym każdy artykuł nadpisywał ten sam wpis (ID=1)!
Dlatego zamiast pytać WordPressa "czy to już jest?", sami prowadzimy własną,
lokalną listę (plik mapa_id.json) z zapisanym: joomla_id -> id_w_wordpressie.

Zanim odpalisz:
- Zainstaluj bibliotekę requests:  pip install requests --break-system-packages
- Uzupełnij dane w sekcji KONFIGURACJA poniżej
- W WordPressie: Użytkownicy -> Twój profil -> Hasła aplikacji -> wygeneruj nowe hasło
  (to NIE jest twoje zwykłe hasło do WP, tylko specjalne dla API)

WAŻNE PRZED PONOWNYM ODPALENIEM:
Skoro poprzednia (wadliwa) wersja skryptu nadpisywała cały czas wpis ID=1,
ten jeden wpis w Twoim WP ma teraz treść ostatniego przetworzonego artykułu.
Najprościej: usuń go ręcznie w panelu WP (Wpisy -> najedź na wpis -> Kosz),
a potem odpal ten poprawiony skrypt od zera - stworzy wszystko poprawnie.

WAŻNE - PRZY PRZEJŚCIU NA NOWY SERWER:
Za każdym razem, gdy zmieniasz WP_URL na inny serwer (np. z testu lokalnego
na serwer docelowy), koniecznie:
1. Wygeneruj NOWE hasło aplikacji na TYM serwerze (stare z innego serwera
   nie zadziała, nawet jeśli login jest taki sam)
2. Usuń albo przenieś stary plik mapa_id.json - ID postów są różne
   na każdej instalacji WP, więc stara mapa wprowadzi bałagan
3. Sprawdź działanie NAJPIERW komendą curl przed odpaleniem tego skryptu:
   curl -u "TWOJ_LOGIN:TWOJE_HASLO" TWOJ_WP_URL/wp-json/wp/v2/users/me
   Jeśli to nie zwróci Twoich danych w JSON, skrypt też nie zadziała.
"""

import json
import os
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# KONFIGURACJA - to musisz uzupełnić swoimi danymi
# ============================================================

WP_URL = "https://nowa.wroclawskakomunikacja.pl"  # adres Twojego WordPressa (bez ukośnika na końcu)
WP_USER = os.environ.get("WP_USER", "admin")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "")  # ustaw przed uruchomieniem: export WP_APP_PASSWORD="..."

ADRES_STAREJ_STRONY = "https://stara.wroclawskakomunikacja.pl"  # do zbudowania pełnych starych URL-i

PLIK_Z_DANYMI = "artykuly_przetworzone.json"  # plik JSON z danymi do zaimportowania (wynik transformuj_jos_content.py)
PLIK_MAPY_ID = "mapa_id.json"  # tu skrypt sam zapisuje powiązania joomla_id -> id_w_wp
PLIK_MAPOWANIA_IMION = "autorzy_mapowanie.json"       # joomla_id_autora -> imię i nazwisko (wypełnione ręcznie)
PLIK_AUTOROW_ARTYKULOW = "do_uzupelnienia_pozniej.json"  # joomla_id_artykulu -> joomla_id_autora

LICZBA_WATKOW = 8  # ile artykułów wysyłamy RÓWNOLEGLE naraz - 8 to bezpieczny start,
                    # nie za dużo dla współdzielonego hostingu, a już zauważalnie szybciej

# Dane do logowania - requests wysyła je przy każdym zapytaniu do API
AUTH = (WP_USER, WP_APP_PASSWORD)

# Sesja HTTP wielokrotnego użytku - zamiast nawiązywać nowe połączenie za każdym
# razem (co jest wolne), requests utrzymuje jedno otwarte połączenie i go reużywa.
# To samo w sobie daje odczuwalne przyspieszenie przy setkach zapytań pod rząd.
SESJA = requests.Session()
SESJA.auth = AUTH

# Blokada (lock) do bezpiecznego zapisu współdzielonych danych (cache, mapa_id)
# z wielu wątków naraz - bez tego dwa wątki mogłyby jednocześnie próbować
# stworzyć ten sam tag/kategorię i skończyć z duplikatami
BLOKADA = threading.Lock()


# ============================================================
# FUNKCJE POMOCNICZE - obsługa lokalnej mapy ID (zamiast pytania WP)
# ============================================================

def wczytaj_mape_id():
    """
    Wczytuje lokalny plik z mapowaniem "typ_joomla_id" -> id_w_wordpressie.
    Jeśli plik jeszcze nie istnieje (pierwsze uruchomienie), zwraca pusty słownik.

    UWAGA: klucz mapy to "typ_joomlaID" (np. "artykul_58" albo "pojazd_58"),
    NIE sam joomla_id. To ważne, bo artykuły i pojazdy pochodzą z TEJ SAMEJ
    tabeli w Joomli (te same numery ID) - artykuł "Ikarus 280.26" ma joomla_id=58
    i istnieje jako zwykły Post w WP, ale chcemy GO TAKŻE zaimportować jako
    osobny wpis w CPT "pojazd". Gdyby mapa używała samego joomla_id jako klucza,
    obie operacje próbowałyby "zaktualizować" ten sam wpis, mimo że to dwa
    różne typy treści w WP (co kończy się błędem 404 - zły typ pod tym ID).

    Dla wstecznej zgodności: jeśli w starym pliku są klucze bez podkreślnika
    (czyli z czasów gdy mapa zawierała tylko artykuły), traktujemy je jako
    "artykul_<id>".
    """
    if not os.path.exists(PLIK_MAPY_ID):
        return {}

    with open(PLIK_MAPY_ID, "r", encoding="utf-8") as plik:
        surowa_mapa = json.load(plik)

    mapa = {}
    for klucz, wartosc in surowa_mapa.items():
        if "_" not in klucz:
            klucz = f"artykul_{klucz}"  # migracja starego formatu klucza
        mapa[klucz] = wartosc
    return mapa


def zapisz_mape_id(mapa):
    """
    Zapisuje aktualny stan mapy joomla_id -> id_w_wordpressie na dysk.
    Wywołujemy to po KAŻDYM udanym imporcie, żeby w razie przerwania
    skryptu (np. Ctrl+C w połowie) nic nie zgubić - można odpalić od nowa
    i skrypt sam pominie już zaimportowane rekordy.
    """
    with open(PLIK_MAPY_ID, "w", encoding="utf-8") as plik:
        json.dump(mapa, plik, ensure_ascii=False, indent=2)


# ============================================================
# OBSŁUGA KATEGORII - WordPress wymaga ID kategorii, nie nazwy tekstowej,
# więc musimy najpierw sprawdzić czy kategoria istnieje, a jeśli nie - stworzyć ją
# ============================================================

# Tu trzymamy w pamięci już sprawdzone/utworzone kategorie w trakcie działania skryptu,
# żeby nie odpytywać WP o to samo po kilkaset razy (np. "Aktualności" powtarza się
# w 548 artykułach - bez cache sprawdzalibyśmy to za każdym razem od nowa)
CACHE_KATEGORII = {}
CACHE_TAGOW = {}
CACHE_TAKSONOMII_POJAZDU = {}  # {"typ_pojazdu": {"autobus": 5, ...}, "status_taboru": {...}, "producent": {...}}


def znajdz_lub_utworz_termin_taksonomii(nazwa_taksonomii, nazwa_terminu, proba=1):
    """
    Uniwersalna wersja znajdz_lub_utworz_kategorie/tag - działa dla DOWOLNEJ
    taksonomii custom post type (np. "typ_pojazdu", "status_taboru", "producent"),
    pod warunkiem że REST base tej taksonomii to dokładnie jej nazwa
    (czyli endpoint /wp-json/wp/v2/<nazwa_taksonomii>).
    """
    if not nazwa_terminu:
        return None

    cache = CACHE_TAKSONOMII_POJAZDU.setdefault(nazwa_taksonomii, {})
    klucz_cache = nazwa_terminu.strip().lower()

    with BLOKADA:
        if klucz_cache in cache:
            return cache[klucz_cache]

    url = f"{WP_URL}/wp-json/wp/v2/{nazwa_taksonomii}"
    odpowiedz = SESJA.post(url, json={"name": nazwa_terminu})

    if odpowiedz.status_code == 201:
        nowy_termin = odpowiedz.json()
        with BLOKADA:
            cache[klucz_cache] = nowy_termin["id"]
        return nowy_termin["id"]
    elif odpowiedz.status_code == 400 and "term_exists" in odpowiedz.text:
        id_istniejacego = odpowiedz.json().get("data", {}).get("term_id")
        if id_istniejacego:
            with BLOKADA:
                cache[klucz_cache] = id_istniejacego
            return id_istniejacego
        return None
    elif proba < 3:
        return znajdz_lub_utworz_termin_taksonomii(nazwa_taksonomii, nazwa_terminu, proba + 1)
    else:
        print(f"    [UWAGA] Nie udało się utworzyć terminu '{nazwa_terminu}' w taksonomii '{nazwa_taksonomii}': {odpowiedz.text}")
        return None


def wczytaj_taksonomie_pojazdu():
    """Pobiera istniejące terminy taksonomii pojazdu na starcie, tak jak kategorie/tagi."""
    for nazwa_taksonomii in ("typ_pojazdu", "status_taboru", "producent"):
        terminy = pobierz_wszystkie_terminy(nazwa_taksonomii)
        CACHE_TAKSONOMII_POJAZDU[nazwa_taksonomii] = {
            nazwa.strip().lower(): id_ for nazwa, id_ in terminy.items()
        }
        print(f"  Wczytano {len(terminy)} terminów taksonomii '{nazwa_taksonomii}'")


def pobierz_wszystkie_terminy(endpoint):
    """
    Pobiera WSZYSTKIE istniejące kategorie albo tagi (endpoint = "categories" albo "tags")
    JEDNYM przebiegiem na starcie, zamiast sprawdzać każdą nazwę osobnym zapytaniem GET
    w trakcie importu. To duża oszczędność czasu - dla 31 kategorii i ~800 unikalnych
    tagów to setki zaoszczędzonych zapytań sieciowych.
    """
    wszystkie = {}
    strona = 1
    while True:
        url = f"{WP_URL}/wp-json/wp/v2/{endpoint}"
        odpowiedz = SESJA.get(url, params={"per_page": 100, "page": strona})
        if odpowiedz.status_code != 200:
            break
        wyniki = odpowiedz.json()
        if not wyniki:
            break
        for term in wyniki:
            wszystkie[term["name"]] = term["id"]
        strona += 1
    return wszystkie


def znajdz_lub_utworz_kategorie(nazwa_kategorii):
    """
    Zwraca ID kategorii w WordPressie o podanej nazwie.
    Najpierw sprawdza w cache (wczytanym raz na starcie) - jeśli nie ma,
    tworzy nową (rzadki przypadek, tylko dla kategorii, których nie było
    jeszcze w WP przy starcie skryptu).
    """
    if not nazwa_kategorii or nazwa_kategorii.startswith("[nieznana"):
        return None

    with BLOKADA:
        if nazwa_kategorii in CACHE_KATEGORII:
            return CACHE_KATEGORII[nazwa_kategorii]

    url = f"{WP_URL}/wp-json/wp/v2/categories"
    odpowiedz = SESJA.post(url, json={"name": nazwa_kategorii})

    if odpowiedz.status_code == 201:
        nowa_kategoria = odpowiedz.json()
        with BLOKADA:
            CACHE_KATEGORII[nazwa_kategorii] = nowa_kategoria["id"]
        print(f"    (utworzono nową kategorię w WP: '{nazwa_kategorii}')")
        return nowa_kategoria["id"]
    elif odpowiedz.status_code == 400 and "term_exists" in odpowiedz.text:
        # Dwa wątki próbowały utworzyć tę samą kategorię naraz - jeden już to zrobił,
        # WP zwraca błąd "już istnieje" razem z ID, którego możemy użyć
        id_istniejacej = odpowiedz.json().get("data", {}).get("term_id")
        if id_istniejacej:
            with BLOKADA:
                CACHE_KATEGORII[nazwa_kategorii] = id_istniejacej
            return id_istniejacej
        return None
    else:
        print(f"    [UWAGA] Nie udało się utworzyć kategorii '{nazwa_kategorii}': {odpowiedz.text}")
        return None


# ============================================================
# OBSŁUGA AUTORÓW - podpinamy prawdziwego autora zamiast domyślnego "admin".
# W przeciwieństwie do kategorii, tu NIE tworzymy nowych kont - konta autorów
# muszą już istnieć w WP (widziałeś je wcześniej na liście użytkowników).
# Budujemy to mapowanie RAZ, na starcie skryptu, a nie w locie dla każdego
# artykułu - stąd ta funkcja jest wywoływana osobno w main(), nie w
# zbuduj_dane_artykulu jak kategorie.
# ============================================================

def pobierz_wszystkich_userow_z_wp():
    """Pobiera pełną listę użytkowników WP (obsługuje stronicowanie, gdyby było ich >100)."""
    wszyscy = []
    strona = 1
    while True:
        url = f"{WP_URL}/wp-json/wp/v2/users"
        odpowiedz = SESJA.get(url, params={"per_page": 100, "page": strona, "context": "edit"})
        if odpowiedz.status_code != 200:
            break
        wyniki = odpowiedz.json()
        if not wyniki:
            break
        wszyscy.extend(wyniki)
        strona += 1
    return wszyscy


def zbuduj_mape_autorow():
    """
    Zwraca słownik {joomla_id_artykulu: id_autora_w_wp}, budowany w 3 krokach:
    1. joomla_id_autora -> imię i nazwisko (z autorzy_mapowanie.json)
    2. imię i nazwisko -> id w WP (pytamy WordPressa o listę użytkowników)
    3. joomla_id_artykulu -> joomla_id_autora (z do_uzupelnienia_pozniej.json)
    Łączymy to w jedno mapowanie, gotowe do szybkiego użycia dla każdego artykułu.
    """
    if not os.path.exists(PLIK_MAPOWANIA_IMION) or not os.path.exists(PLIK_AUTOROW_ARTYKULOW):
        print("[INFO] Brak plików do mapowania autorów - wszystkie artykuły zostaną z domyślnym autorem")
        return {}

    with open(PLIK_MAPOWANIA_IMION, "r", encoding="utf-8") as plik:
        mapowanie_imion = json.load(plik)  # {"62": {"imie_nazwisko": "...", ...}, ...}

    with open(PLIK_AUTOROW_ARTYKULOW, "r", encoding="utf-8") as plik:
        autorzy_artykulow = json.load(plik)  # [{"joomla_id": 6, "created_by_id": "62", ...}, ...]

    print("Pobieram listę użytkowników z WordPressa (do dopasowania autorów)...")
    userzy_wp = pobierz_wszystkich_userow_z_wp()
    nazwa_do_id_wp = {u["name"].strip().lower(): u["id"] for u in userzy_wp}

    # Krok 1+2: joomla_id_autora -> id w WP
    joomla_autor_do_wp_id = {}
    for joomla_id_autora, dane in mapowanie_imion.items():
        imie = dane.get("imie_nazwisko")
        if not imie:
            continue
        klucz = imie.strip().lower()
        if klucz in nazwa_do_id_wp:
            joomla_autor_do_wp_id[joomla_id_autora] = nazwa_do_id_wp[klucz]
        else:
            print(f"  [UWAGA] Brak konta w WP dla autora: '{imie}' (Joomla ID {joomla_id_autora})")

    # Krok 3: joomla_id_artykulu -> id_autora_w_wp
    mapa_artykul_do_autora = {}
    for wpis in autorzy_artykulow:
        joomla_id_autora = str(wpis.get("created_by_id"))
        id_autora_wp = joomla_autor_do_wp_id.get(joomla_id_autora)
        if id_autora_wp:
            mapa_artykul_do_autora[wpis["joomla_id"]] = id_autora_wp

    print(f"Dopasowano autorów dla {len(mapa_artykul_do_autora)} z {len(autorzy_artykulow)} artykułów\n")
    return mapa_artykul_do_autora


def znajdz_lub_utworz_tag(nazwa_tagu, proba=1):
    """
    Działa jak znajdz_lub_utworz_kategorie, ale dla tagów (endpoint /tags).
    Ponawia próbę (do 3 razy), jeśli tworzenie się nie uda - przy kilku wątkach
    naraz próbujących stworzyć wiele nowych tagów jednocześnie, czasem dochodzi
    do chwilowego konfliktu zapisu w bazie, który znika przy drugiej próbie.
    """
    if not nazwa_tagu:
        return None

    with BLOKADA:
        if nazwa_tagu in CACHE_TAGOW:
            return CACHE_TAGOW[nazwa_tagu]

    url = f"{WP_URL}/wp-json/wp/v2/tags"
    odpowiedz = SESJA.post(url, json={"name": nazwa_tagu})

    if odpowiedz.status_code == 201:
        nowy_tag = odpowiedz.json()
        with BLOKADA:
            CACHE_TAGOW[nazwa_tagu] = nowy_tag["id"]
        return nowy_tag["id"]
    elif odpowiedz.status_code == 400 and "term_exists" in odpowiedz.text:
        id_istniejacego = odpowiedz.json().get("data", {}).get("term_id")
        if id_istniejacego:
            with BLOKADA:
                CACHE_TAGOW[nazwa_tagu] = id_istniejacego
            return id_istniejacego
        return None
    elif proba < 3:
        # Nie udało się i nie jest to zwykłe "już istnieje" - spróbuj ponownie
        # (może to być chwilowy konflikt zapisu przy wielu wątkach naraz)
        print(f"    [PONOWNA PRÓBA {proba+1}/3] tag '{nazwa_tagu}': {odpowiedz.status_code} {odpowiedz.text[:200]}")
        return znajdz_lub_utworz_tag(nazwa_tagu, proba + 1)
    else:
        print(f"    [UWAGA] Nie udało się utworzyć tagu '{nazwa_tagu}' po 3 próbach: {odpowiedz.text}")
        return None


def wyslij_wpis(typ_endpointu, dane_wpisu, istniejace_id=None):
    """
    Wysyła wpis do WordPressa - tworzy nowy (POST) albo aktualizuje istniejący (PUT).

    typ_endpointu - np. "posts" albo "pojazd"
    dane_wpisu - słownik z danymi w formacie oczekiwanym przez WP REST API
    istniejace_id - jeśli podane, aktualizujemy TEN KONKRETNY wpis (z mapy ID),
                    zamiast tworzyć nowy
    """
    if istniejace_id:
        url = f"{WP_URL}/wp-json/wp/v2/{typ_endpointu}/{istniejace_id}"
        odpowiedz = SESJA.post(url, json=dane_wpisu)
        akcja = "Zaktualizowano"
    else:
        url = f"{WP_URL}/wp-json/wp/v2/{typ_endpointu}"
        odpowiedz = SESJA.post(url, json=dane_wpisu)
        akcja = "Utworzono"

    if odpowiedz.status_code in (200, 201):
        wynik = odpowiedz.json()
        return akcja, wynik["id"]
    else:
        return None, f"{odpowiedz.status_code} na {url}: {odpowiedz.text}"


# ============================================================
# LOGIKA MAPOWANIA - tu decydujemy jak dane z Joomli
# przekładają się na strukturę w WordPressie
# ============================================================

def zbuduj_pelny_stary_url(sciezka_wzgledna):
    """
    Zamienia względną ścieżkę z Joomli (np. "/component/content/article/54/1994-tytul")
    na pełny adres URL (np. "https://stara.wroclawskakomunikacja.pl/component/...").

    Dlaczego pełny: pole "zrodlowy_url_joomla" w SCF jest typu "url", a takie pola
    zwykle wymagają pełnego adresu ze schematem (https://), nie samej ścieżki.
    Pełny adres jest też potrzebny później przy budowaniu przekierowań 301.
    """
    if not sciezka_wzgledna:
        return ""
    if sciezka_wzgledna.startswith(("http://", "https://")):
        return sciezka_wzgledna  # już jest pełnym adresem, nic nie zmieniamy
    return f"{ADRES_STAREJ_STRONY.rstrip('/')}/{sciezka_wzgledna.lstrip('/')}"


def zbuduj_dane_artykulu(rekord, id_autora_wp=None):
    """
    Zamienia rekord typu 'artykul' z naszego JSON-a na format,
    jaki rozumie WP REST API dla zwykłych postów.
    """
    dane = {
        "title": rekord["tytul"],
        "content": rekord.get("tresc", ""),
        "status": "publish",
        # UWAGA: "_joomla_id" i "zrodlowy_url_joomla" to pola SCF, NIE zwykłe pola meta!
        # Wcześniej wysyłaliśmy je pod kluczem "meta" i WordPress je po cichu ignorował -
        # dlatego w panelu były puste. Muszą iść pod kluczem "acf", tak jak reszta pól SCF.
        "acf": {
            "_joomla_id": rekord["joomla_id"],
            "zrodlowy_url_joomla": zbuduj_pelny_stary_url(rekord["old_url"]),
        },
    }

    # Podpinamy kategorię, jeśli ją znamy (WP wymaga ID, nie nazwy - dlatego
    # wywołujemy funkcję, która sama znajdzie albo utworzy kategorię)
    id_kategorii = znajdz_lub_utworz_kategorie(rekord.get("kategoria"))
    if id_kategorii:
        dane["categories"] = [id_kategorii]

    # Podpinamy prawdziwego autora, jeśli udało się go dopasować
    # (jeśli nie - WP i tak przypisze domyślnie konto, którym się logujemy przez API)
    if id_autora_wp:
        dane["author"] = id_autora_wp

    # Podpinamy tagi. WAŻNE: wysyłamy pole "tags" ZAWSZE (nawet pustą listę),
    # bo jeśli go nie wyślemy, WordPress zostawia to, co już tam było wcześniej -
    # a to dokładnie przez to stare, śmieciowe tagi z błędnego importu nigdy
    # nie znikały z artykułów, które w Joomli w ogóle nie miały tagów.
    nazwy_tagow = rekord.get("tagi") or []
    id_tagow = [znajdz_lub_utworz_tag(nazwa) for nazwa in nazwy_tagow]
    id_tagow = [i for i in id_tagow if i]  # odfiltruj te, które się nie udały
    dane["tags"] = id_tagow

    return dane


def zbuduj_dane_pojazdu(rekord):
    """
    Zamienia rekord typu 'pojazd' na format dla custom post type "pojazd".

    WAŻNE (ustalone na podstawie prawdziwych przykładowych wpisów w WP):
    - "typ_pojazdu", "status_taboru", "producent" to TAKSONOMIE (jak kategorie
      dla zwykłych postów), NIE pola SCF - przypisujemy je na poziomie posta,
      dokładnie tak jak "categories" dla artykułów.
    - Reszta danych technicznych (długość, moc silnika itd.) idzie pod klucz "acf".
    """
    # Pola migracyjne (_joomla_id, zrodlowy_url_joomla) to też pola SCF, więc
    # dokładamy je do tego samego słownika co dane techniczne, pod kluczem "acf".
    # Kopiujemy słownik, żeby nie modyfikować oryginalnych danych wczytanych z pliku.
    pola_acf = dict(rekord["pola"])
    pola_acf["_joomla_id"] = rekord["joomla_id"]
    pola_acf["zrodlowy_url_joomla"] = zbuduj_pelny_stary_url(rekord["old_url"])

    dane = {
        "title": rekord["tytul"],
        "status": "publish",
        # Wcześniej tego pola tu nie było, więc każdy zaimportowany pojazd
        # miał pustą treść w WP - opis wyciąga teraz parsuj_pojazdy.py
        # (funkcja wyciagnij_opis) z tekstu między nagłówkami "OPIS POJAZDU"
        # a "DANE PODSTAWOWE" w oryginalnym artykule Joomli.
        "content": rekord.get("opis", ""),
        "acf": pola_acf,
    }

    id_typu_pojazdu = znajdz_lub_utworz_termin_taksonomii("typ_pojazdu", rekord.get("typ_pojazdu"))
    if id_typu_pojazdu:
        dane["typ_pojazdu"] = [id_typu_pojazdu]

    id_statusu = znajdz_lub_utworz_termin_taksonomii("status_taboru", rekord.get("status_taboru"))
    if id_statusu:
        dane["status_taboru"] = [id_statusu]

    id_producenta = znajdz_lub_utworz_termin_taksonomii("producent", rekord.get("producent"))
    if id_producenta:
        dane["producent"] = [id_producenta]

    return dane


# ============================================================
# GŁÓWNA PĘTLA - to się faktycznie wykonuje, gdy odpalisz skrypt
# ============================================================

def przetworz_jeden_rekord(rekord, mapa_id, mapa_autorow):
    """
    Przetwarza jeden rekord od początku do końca - to jest "jednostka pracy",
    którą wątki będą wykonywać równolegle. Zwraca (joomla_id, nowe_id_w_wp)
    przy sukcesie, albo (joomla_id, None) przy błędzie.
    """
    typ = rekord["typ"]
    joomla_id = rekord["joomla_id"]
    klucz_mapy = f"{typ}_{joomla_id}"  # np. "pojazd_58" - odróżnia od "artykul_58"

    if typ == "artykul":
        typ_endpointu = "posts"
        id_autora_wp = mapa_autorow.get(joomla_id)
        dane_wpisu = zbuduj_dane_artykulu(rekord, id_autora_wp)
    elif typ == "pojazd":
        typ_endpointu = "pojazd"
        dane_wpisu = zbuduj_dane_pojazdu(rekord)
    else:
        print(f"  [POMINIĘTO] Nieznany typ rekordu: {typ} (joomla_id={joomla_id})")
        return klucz_mapy, None

    istniejace_id = mapa_id.get(klucz_mapy)
    akcja, wynik = wyslij_wpis(typ_endpointu, dane_wpisu, istniejace_id)

    if akcja:
        print(f"  [OK] {akcja}: '{rekord['tytul']}' (joomla_id={joomla_id}) -> WP ID={wynik}")
        return klucz_mapy, wynik
    else:
        print(f"  [BŁĄD] '{rekord['tytul']}' (joomla_id={joomla_id}): {wynik}")
        return klucz_mapy, None


def main():
    # Krok 1: wczytaj dane z pliku JSON
    with open(PLIK_Z_DANYMI, "r", encoding="utf-8") as plik:
        rekordy = json.load(plik)

    print(f"Wczytano {len(rekordy)} rekordów z pliku {PLIK_Z_DANYMI}")

    # Krok 2: wczytaj naszą własną mapę już zaimportowanych rekordów
    mapa_id = wczytaj_mape_id()
    print(f"Wczytano mapę {len(mapa_id)} już zaimportowanych wcześniej rekordów")

    # Krok 2b: zbuduj mapowanie autorów (joomla_id_artykulu -> id_autora_w_wp)
    mapa_autorow = zbuduj_mape_autorow()

    # Krok 2c: pobierz WSZYSTKIE istniejące kategorie i tagi JEDNYM przebiegiem,
    # zamiast sprawdzać każdą osobno w trakcie - to jest główne źródło przyspieszenia
    print("Pobieram listę istniejących kategorii...")
    CACHE_KATEGORII.update(pobierz_wszystkie_terminy("categories"))
    print(f"  Wczytano {len(CACHE_KATEGORII)} kategorii")

    print("Pobieram listę istniejących tagów...")
    CACHE_TAGOW.update(pobierz_wszystkie_terminy("tags"))
    print(f"  Wczytano {len(CACHE_TAGOW)} tagów\n")

    print("Pobieram listę istniejących taksonomii pojazdu...")
    wczytaj_taksonomie_pojazdu()
    print()

    # Krok 3: przetwarzamy rekordy RÓWNOLEGLE (kilka naraz zamiast jeden po drugim)
    ukonczone = 0
    with ThreadPoolExecutor(max_workers=LICZBA_WATKOW) as executor:
        zadania = {
            executor.submit(przetworz_jeden_rekord, rekord, mapa_id, mapa_autorow): rekord
            for rekord in rekordy
        }

        for zadanie in as_completed(zadania):
            klucz_mapy, nowe_id = zadanie.result()
            ukonczone += 1

            if nowe_id:
                # Zapis do mapy pod ochroną blokady - kilka wątków może próbować
                # zapisać plik w tym samym momencie, blokada zapobiega bałaganowi
                with BLOKADA:
                    mapa_id[klucz_mapy] = nowe_id
                    zapisz_mape_id(mapa_id)

            if ukonczone % 50 == 0:
                print(f"--- Postęp: {ukonczone}/{len(rekordy)} ---")

    print(f"\nGotowe! Przetworzono {ukonczone}/{len(rekordy)} rekordów.")
    print("Sprawdź w panelu WordPressa czy wpisy się pojawiły.")


if __name__ == "__main__":
    main()
