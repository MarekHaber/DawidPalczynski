"""
SKRYPT TRANSFORMACJI: surowy eksport jos_content.json -> format do importu
============================================================================

Co robi:
1. Wczytuje surowy eksport tabeli jos_content (z phpMyAdmin, format "Export to JSON")
2. Wczytuje jos_categories -> zamienia numer catid na prawdziwą nazwę kategorii
3. Wczytuje jos_contentitem_tag_map -> podpina do artykułu listę ID tagów
   (same nazwy tagów dodamy, jak dostaniemy eksport jos_tags)
4. Dla każdego artykułu wyciąga potrzebne dane i zamienia na "płaski" format,
   jaki rozumie nasz skrypt import_do_wordpress.py
5. Zapisuje wynik do nowego pliku JSON

Czego NA RAZIE nie robi (bo brakuje danych źródłowych):
- Nie tłumaczy ID tagów na nazwy tagów - potrzebny eksport jos_tags
- Nie tłumaczy ID autora na imię i nazwisko - potrzebny eksport jos_users
- Nie zna dokładnego formatu "ładnych" URL-i Joomli (SEF) - do zweryfikowania ręcznie

Te rzeczy dopiszemy, jak Osoba 1 wyeksportuje odpowiednie tabele / to sprawdzimy.
"""

import json

PLIK_CONTENT = "jos_content.json"
PLIK_CATEGORIES = "jos_categories.json"       # opcjonalny - jeśli brak, catid zostanie numerem
PLIK_TAG_MAP = "jos_contentitem_tag_map.json"  # opcjonalny - jeśli brak, artykuł nie będzie miał tagów
PLIK_WYJSCIOWY = "artykuly_przetworzone.json"

# Jakie statusy artykułów migrujemy?
# state: "1" = opublikowany, "0" = niepublikowany, "-2" = kosz, "2" = zarchiwizowany
# Na start bierzemy tylko opublikowane - reszta do ustalenia z Michałem
STATUSY_DO_MIGRACJI = {"1"}


def wyciagnij_dane_obrazka(images_json_string):
    """
    Pole 'images' w Joomli to zagnieżdżony JSON (string wewnątrz stringa).
    Wyciągamy z niego ścieżkę do zdjęcia głównego i podpis/autora.
    """
    try:
        images = json.loads(images_json_string)
    except (json.JSONDecodeError, TypeError):
        return None, None, None

    # Joomla ma osobne obrazki dla "wstępu" (intro) i "pełnej treści" (fulltext)
    # Bierzemy fulltext jeśli jest, inaczej intro
    sciezka = images.get("image_fulltext") or images.get("image_intro") or ""
    podpis = images.get("image_fulltext_caption") or images.get("image_intro_caption") or ""
    alt = images.get("image_fulltext_alt") or images.get("image_intro_alt") or ""

    return sciezka, podpis, alt


def wczytaj_blok_tabeli(nazwa_pliku, nazwa_tabeli):
    """
    Wczytuje plik eksportu phpMyAdmin i zwraca listę rekordów z danej tabeli.
    Zwraca None jeśli plik nie istnieje - dzięki temu skrypt działa nawet
    bez opcjonalnych plików (kategorii/tagów), tylko z mniejszą ilością danych.
    """
    try:
        with open(nazwa_pliku, "r", encoding="utf-8") as plik:
            surowe_dane = json.load(plik)
    except FileNotFoundError:
        print(f"[INFO] Nie znaleziono pliku {nazwa_pliku} - pomijam ten krok wzbogacania danych")
        return None

    for sekcja in surowe_dane:
        if sekcja.get("type") == "table" and sekcja.get("name") == nazwa_tabeli:
            return sekcja["data"]

    print(f"[UWAGA] Plik {nazwa_pliku} nie zawiera tabeli {nazwa_tabeli}")
    return None


def zbuduj_slownik_kategorii(rekordy_kategorii):
    """
    Zamienia listę kategorii na słownik {catid: nazwa_kategorii}.
    Bierzemy tylko kategorie artykułów (extension == 'com_content').
    """
    if rekordy_kategorii is None:
        return {}

    return {
        r["id"]: r["title"]
        for r in rekordy_kategorii
        if r["extension"] == "com_content"
    }


def zbuduj_mape_tagow_artykulow(rekordy_tag_map):
    """
    Zamienia listę powiązań artykuł<->tag na słownik {id_artykulu: [id_tagu, id_tagu, ...]}.

    UWAGA: w tabeli jos_contentitem_tag_map pole 'content_item_id' to prawdziwe ID
    artykułu (czyli to samo co 'id' w jos_content). Pole 'core_content_id' to inny,
    wewnętrzny numer Joomli (UCM) i NIE pasuje do jos_content.id - nie używamy go.
    """
    if rekordy_tag_map is None:
        return {}

    mapa = {}
    for r in rekordy_tag_map:
        if r["type_alias"] != "com_content.article":
            continue  # interesują nas tylko tagi na artykułach, nie np. na kontaktach
        id_artykulu = int(r["content_item_id"])
        mapa.setdefault(id_artykulu, []).append(r["tag_id"])
    return mapa


def wyczysc_html(tekst):
    """
    Treść z Joomli często ma dużo zagnieżdżonych <span> ze starymi stylami
    (np. z Worda/Google Docs wklejonego kiedyś do edytora).
    Na razie zostawiamy HTML tak jak jest - WordPress i tak go wyświetli.
    W razie potrzeby tutaj można dodać czyszczenie zbędnych tagów.
    """
    return tekst or ""


def przetworz_rekord(rekord, slownik_kategorii, mapa_tagow):
    """
    Zamienia jeden rekord z jos_content na "płaski" format do importu.
    """
    sciezka_obrazka, podpis_obrazka, alt_obrazka = wyciagnij_dane_obrazka(rekord.get("images", ""))

    id_artykulu = int(rekord["id"])
    catid = rekord["catid"]
    # Jeśli mamy słownik kategorii - podstawiamy nazwę, jeśli nie - zostawiamy numer
    nazwa_kategorii = slownik_kategorii.get(catid, f"[nieznana kategoria catid={catid}]")

    # Lista ID tagów przypiętych do tego artykułu (nazwy dopiszemy jak będzie jos_tags)
    id_tagow = mapa_tagow.get(id_artykulu, [])

    # Łączymy introtext (zajawka) i fulltext (reszta artykułu) w jedną treść,
    # dokładnie tak jak Joomla wyświetla to na stronie artykułu
    tresc = wyczysc_html(rekord.get("introtext", "")) + wyczysc_html(rekord.get("fulltext", ""))

    return {
        "joomla_id": int(rekord["id"]),
        "typ": "artykul",
        "tytul": rekord["title"],
        "alias": rekord["alias"],  # przyda się do zbudowania starego URL-a
        "tresc": tresc,
        "tresc_zajawka": rekord.get("introtext", ""),
        "catid": catid,
        "kategoria": nazwa_kategorii,
        # Tagi i autor: na razie NIE mamy jos_tags ani jos_users, więc zamiast
        # zgadywać, jawnie oznaczamy to jako "do uzupełnienia później".
        # Same numery ID zapisujemy osobno (patrz plik do_uzupelnienia_pozniej.json),
        # żeby nikt przez pomyłkę nie potraktował numeru ID jako gotowej nazwy.
        "tagi": "DO_UZUPELNIENIA" if id_tagow else None,
        "autor_nazwa": "DO_UZUPELNIENIA",
        "data_utworzenia": rekord.get("created"),
        "seo_meta_opis": rekord.get("metadesc", ""),
        "obrazek_glowny": sciezka_obrazka,
        "obrazek_podpis_autor": podpis_obrazka,  # np. "© Łukasz Kuczewski" - WAŻNE, to jest autor zdjęcia!
        "obrazek_alt": alt_obrazka,
        "liczba_wyswietlen": rekord.get("hits"),
        "wyrozniony": rekord.get("featured") == "1",
        # Budujemy przybliżony stary URL na podstawie catid + id + alias
        # (dokładny format zależy od konfiguracji SEF URLs w Joomli - do potwierdzenia)
        "old_url": f"/component/content/article/{rekord['catid']}/{rekord['id']}-{rekord['alias']}",
    }


def main():
    wszystkie_rekordy = wczytaj_blok_tabeli(PLIK_CONTENT, "jos_content")
    if wszystkie_rekordy is None:
        print("[BŁĄD] Bez pliku jos_content nie da się nic zrobić - przerywam")
        return
    print(f"Wczytano {len(wszystkie_rekordy)} rekordów z {PLIK_CONTENT}")

    rekordy_kategorii = wczytaj_blok_tabeli(PLIK_CATEGORIES, "jos_categories")
    slownik_kategorii = zbuduj_slownik_kategorii(rekordy_kategorii)
    print(f"Wczytano nazwy dla {len(slownik_kategorii)} kategorii")

    rekordy_tag_map = wczytaj_blok_tabeli(PLIK_TAG_MAP, "jos_contentitem_tag_map")
    mapa_tagow = zbuduj_mape_tagow_artykulow(rekordy_tag_map)
    print(f"Wczytano powiązania tagów dla {len(mapa_tagow)} artykułów")

    # Filtrujemy tylko te ze statusem, który chcemy migrować
    rekordy_do_migracji = [r for r in wszystkie_rekordy if r["state"] in STATUSY_DO_MIGRACJI]
    pominiete = len(wszystkie_rekordy) - len(rekordy_do_migracji)
    print(f"Do migracji zakwalifikowano: {len(rekordy_do_migracji)} (pominięto {pominiete} wg statusu)")

    przetworzone = [
        przetworz_rekord(r, slownik_kategorii, mapa_tagow)
        for r in rekordy_do_migracji
    ]

    with open(PLIK_WYJSCIOWY, "w", encoding="utf-8") as plik:
        json.dump(przetworzone, plik, ensure_ascii=False, indent=2)

    print(f"Zapisano przetworzone dane do {PLIK_WYJSCIOWY}")

    # Zapisujemy osobno surowe numery ID tagów/autorów per artykuł,
    # żeby móc je dociągnąć drugim skryptem, jak tylko dostaniemy
    # jos_tags i jos_users - bez potrzeby przerabiania wszystkiego od nowa
    do_uzupelnienia = [
        {
            "joomla_id": int(r["id"]),
            "created_by_id": r.get("created_by"),
            "id_tagow": mapa_tagow.get(int(r["id"]), []),
        }
        for r in rekordy_do_migracji
    ]
    with open("do_uzupelnienia_pozniej.json", "w", encoding="utf-8") as plik:
        json.dump(do_uzupelnienia, plik, ensure_ascii=False, indent=2)
    print(f"Zapisano surowe ID tagów/autorów do do_uzupelnienia_pozniej.json (dociągniemy je, jak dostaniemy jos_tags/jos_users)")
    print()
    print("Przykładowy pierwszy rekord po przetworzeniu:")
    print(json.dumps(przetworzone[0], ensure_ascii=False, indent=2)[:800])


if __name__ == "__main__":
    main()
