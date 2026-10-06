# Migracja treści z Joomli do WordPressa

Skrypty, którymi przeniesiono artykuły, pojazdy i zdjęcia ze starej strony (Joomla, `stara.wroclawskakomunikacja.pl`) do nowej (WordPress, `nowa.wroclawskakomunikacja.pl`).

## Kolejność uruchamiania

1. **`transformuj_jos_content.py`** – czyta eksport tabel Joomli z phpMyAdmina (`jos_content.json`, `jos_categories.json`, `jos_contentitem_tag_map.json`) i zamienia go na prosty format `artykuly_przetworzone.json`. Bierze tylko opublikowane artykuły, podstawia nazwy kategorii i wyciąga dane zdjęcia głównego.
2. **`import_do_wordpress.py`** – wysyła artykuły i pojazdy do WordPressa przez REST API i zapisuje w `mapa_id.json`, który rekord z Joomli dostał jakie ID w WordPressie (dzięki temu skrypt można bezpiecznie uruchamiać ponownie bez duplikatów).
3. **`pobierz_i_wgraj_zdjecia.py`** – pobiera zdjęcia główne ze starej strony, wgrywa je do biblioteki mediów WordPressa (z tekstem alternatywnym i podpisem autora zdjęcia) i ustawia jako obrazek wyróżniający. Postęp zapisuje w `mapa_zdjec.json`.

## Pliki danych

- `artykuly_przetworzone.json`, `pojazdy_przetworzone.json` – dane po transformacji, gotowe do importu
- `autorzy_mapowanie.json` – ID autora w Joomli → imię i nazwisko
- `mapa_id.json` – ID w Joomli → ID wpisu w WordPressie

Surowe eksporty bazy Joomli (`jos_*.json`) nie są w repozytorium, bo zawierają też nieopublikowane i usunięte treści.

## Uruchomienie

Skrypty wymagają Pythona 3.9+ i biblioteki `requests` (`pip install requests`). Dane logowania nie są zapisane w kodzie – przed uruchomieniem importu ustaw je w terminalu:

```bash
export WP_USER="admin"
export WP_APP_PASSWORD="hasło aplikacji z WordPressa"
python3 import_do_wordpress.py
python3 pobierz_i_wgraj_zdjecia.py
```

Hasło aplikacji generuje się w WordPressie: Użytkownicy → Profil → Hasła aplikacji.
