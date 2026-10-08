ARBI NEW-1 — NOWY PROJEKT OD ZERA
Repozytorium: xlvlcl/arbi
Strona: https://xlvlcl.github.io/arbi/

JAK WGRAĆ (JEDNORAZOWO)
1. Rozpakuj arbi_NEW_od_zera.zip. Wgraj cały folder fresh do katalogu głównego repozytorium xlvlcl/arbi na gałęzi main. Po wgraniu musi istnieć fresh/scan.py, a nie scan.py bez folderu fresh. Nie wgrywaj samego ZIP-a.
   W GitHub: Code → Add file → Upload files → przeciągnij folder fresh → Commit changes.
2. Otwórz istniejący .github/workflows/surebet.yml → Edit. Zastąp CAŁĄ treść zawartością surebet_NEW.txt i zapisz na main.
3. Otwórz istniejący .github/workflows/watchdog.yml → Edit. Zastąp CAŁĄ treść zawartością watchdog_DISABLED.txt i zapisz na main. Ten plik wyłącza harmonogram starego watchdoga.
   Jeśli są dodatkowe stare workflow skanujące lub publikujące stronę, wyłącz ich harmonogram w Actions, żeby nie nadpisywały nowej publikacji.
4. Settings → Pages → Build and deployment → Source: GitHub Actions.
   Settings → Actions → General → Workflow permissions: Read and write permissions. Zapisz. Jeżeli main ma ochronę zabraniającą botowi zapisu, wynik skanera nie zapisze się w repozytorium — workflow pokaże ten błąd.
5. Zachowaj obecne sekrety w Settings → Secrets and variables → Actions:
   SITE_PASSWORD (wymagane), TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (Telegram), ONESIGNAL_APP_ID + ONESIGNAL_API_KEY (push).
   Nie wpisuj sekretów do plików ani na stronę. Brak sekretów powiadomień nie blokuje samego skanowania. Brak SITE_PASSWORD blokuje publikację.
6. Anuluj pozostałe stare uruchomienia, jeśli jeszcze działają. Actions → Surebet Scanner → Run workflow → main.
   Nowe uruchomienie ma nazwę zaczynającą się od „Arbi NEW-1”. Otwórz jego podsumowanie i poczekaj na publikację Pages.
7. Otwórz https://xlvlcl.github.io/arbi/ i wykonaj twarde odświeżenie (Ctrl+Shift+R). Zaloguj się istniejącym hasłem SITE_PASSWORD.

CO ZOSTAJE ZE STAREJ WERSJI
Nowy workflow uruchamia fresh/scan.py i publikuje fresh/web. Stare docs, app.py, requirements i poprzednia historia wyników nie są używane. Mogą pozostać w repozytorium; nie trzeba ich kasować. Nowa historia powiadomień zaczyna się w fresh/state.json.
Nie zmieniaj nazw workflow: surebet.yml oraz repository_dispatch surebet_scan zachowują zgodność z dotychczasowym zewnętrznym wyzwalaczem. Dla workflow_dispatch wyzwalacz powinien nadal wskazywać surebet.yml i main. Własny harmonogram GitHub w nowym pliku uruchamia się co 5 minut; dotychczasowy zewnętrzny wyzwalacz może dalej działać co 2 minuty. Opóźnienia i kolejka GitHub mogą przesunąć wykonanie.
Komputer nie musi być włączony — wykonanie i publikacja odbywają się na GitHubie.

JAK DZIAŁA NOWA WERSJA
• Jedno pobranie katalogu z publicznego API porównywarki, następnie ograniczona liczba pełnych ofert zdarzeń.
• Kandydaci są wybierani z kompletnych grup rynków. Szczegóły kandydatów z możliwym zyskiem są pobierane drugi raz.
• Uwzględniane są koszty źródła, podatki poszczególnych bukmacherów oraz zaokrąglenia do groszy.
• Surebet jest pokazywany i wysyłany tylko, gdy wyliczony zysk pozostaje dodatni po drugim odczycie źródła. Ponowny odczyt nie jest bezpośrednim potwierdzeniem dostępności kursu na koncie bukmachera.
• Brak dodatnich okazji jest poprawnym wynikiem, jeśli status pokazuje ukończony skan. Liczby wydarzeń i rynków oznaczają katalog, a nie pełny drugi odczyt wszystkich ofert.
• Jeżeli limit szczegółów ograniczy analizę lub część odczytów zawiedzie, status pokazuje skan częściowy.
• Panel pokazuje osobno ostatnią próbę i ostatni udany odczyt. Błąd nie udaje nowego sukcesu. Okazje sprzed ponad 5 minut oraz rozpoczęte zdarzenia są ukrywane.
• Filtry, katalog, kalkulator budżetu, linki do ofert i powiadomienia są napisane od nowa.
• Skrypt używa tylko standardowej biblioteki Python. Nie instaluje przeglądarek ani pakietów pip.

USTAWIENIA
W .github/workflows/surebet.yml:
BANKROLL_PLN: '50' — budżet, dla którego skaner wyszukuje okazje i wysyła alerty. Zmiana budżetu w panelu przelicza już znalezione okazje; nie wykonuje nowego skanu źródła.
MIN_PROFIT_PCT: '0.35' — minimalny wyliczony zysk skanera.
DETAIL_LIMIT: '40' — maksymalna liczba zdarzeń w pierwszej rundzie szczegółów.
SCAN_BUDGET_SECONDS: '85' — budżet czasu na pobieranie danych. Workflow ma także zewnętrzny limit procesu.
BOOKMAKER_TAX_OVERRIDES: '{}' — domyślnie używane są koszty z porównywarki. Jeśli masz potwierdzoną aktywną promocję bez podatku, możesz ustawić JSON z odpowiednim slugiem, np. '{"betclic":0}'. Nie ustawiaj podatku 0 tylko dlatego, że reklamowana jest promocja — musi dotyczyć Twojego konta i danego zakładu.
Dla push domena i ścieżka w panelu OneSignal muszą odpowiadać https://xlvlcl.github.io/arbi/. W panelu nowej strony kliknij „Włącz powiadomienia”.
Panel na GitHub Pages jest statyczny: bramka hasła nie stanowi serwerowej kontroli dostępu do publicznych danych. Klucze Telegram i OneSignal pozostają wyłącznie w sekretach Actions.

WERYFIKACJA PRZED PRZEKAZANIEM
31 testów Python: rynki, podatki, zaokrąglenia, filtr dat, pełny przebieg, drugi odczyt, limit analizy, obsługa awarii i alerty.
40 scenariuszy zgodności kalkulatora JavaScript z Pythonem.
Test logiki panelu: katalog, filtry, stan błędu, szybki odczyt podczas zawieszenia drugiego adresu i brak nakładających się cykli.
Sprawdzenie składni workflow YAML, skryptów bash i Python.
Rzeczywisty skan źródła: 1505 nadchodzących zdarzeń, 8664 grupy rynków, 25 pełnych odczytów, około 59 sekund, status ok, brak błędów, 0 potwierdzonych okazji po kosztach. To test aktualnych danych, a nie sztucznie dodane surebety.
Publikacja na Twoim GitHubie i dostarczenie alertów z Twoimi sekretami wymagają pierwszego uruchomienia po wgraniu. Nie były uruchamiane z lokalnego środowiska.

GDY PIERWSZE URUCHOMIENIE SIĘ NIE UDA
Otwórz nieudany krok w Actions. Brak SITE_PASSWORD → uzupełnij sekret. Brak prawa zapisu main → ustaw prawa Actions/ochronę gałęzi. Błąd Pages → upewnij się, że Source to GitHub Actions. Problem odczytu źródła → workflow publikuje bieżący komunikat i zachowuje czas ostatniego poprawnego wyniku; log jest w artefakcie arbi-new-log.
