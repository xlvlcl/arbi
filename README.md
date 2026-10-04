# Surebet Alert — Playwright + obecny wygląd

Ta wersja łączy:
- silnik Playwright z wcześniejszej wersji, która działała lokalnie,
- obecny ciemny interfejs GitHub Pages,
- automatyczny workflow GitHub Actions,
- Telegram,
- ochronę przed opublikowaniem pustego skanu.

## Dlaczego poprzednia strona się nie odświeżała

Workflow miał tylko `workflow_dispatch`, czyli uruchamiał się wyłącznie ręcznie.
Ten projekt ma także `schedule` co około 5 minut oraz `repository_dispatch`
do późniejszego podłączenia zewnętrznego schedulera.

GitHub Pages sam nie uruchamia Pythona. Strona tylko pobiera świeży
`docs/data/latest.json`. Nowy JSON pojawia się dopiero po zakończonym skanie
i deployu Actions.

## Pierwszy test

1. Wgraj cały projekt do repozytorium tak, aby `.github`, `app`, `docs`,
   `data`, `scanner.py` i `requirements.txt` były w katalogu głównym.
2. W `Settings -> Secrets and variables -> Actions` dodaj:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. W `Settings -> Pages -> Source` wybierz `GitHub Actions`.
4. Wejdź w `Actions -> Surebet Scanner -> Run workflow`.
5. Jeżeli skan odczyta 0 wydarzeń, workflow kończy się błędem i NIE nadpisuje
   ostatniej dobrej strony zerami.

## Automatyczne odświeżanie

Workflow ma cron:
`3-58/5 * * * *`

To daje próbę uruchomienia co około 5 minut. GitHub może opóźniać cron.
Dlatego workflow obsługuje też `repository_dispatch: surebet_scan`.
Po potwierdzeniu, że Playwright działa na GitHubie, można podpiąć zewnętrzny
scheduler i wywoływać go częściej bez polegania wyłącznie na harmonogramie GitHuba.

Frontend sprawdza nowy `latest.json` co 5 sekund, ale to nie oznacza skanu co
5 sekund — pokazuje nowy wynik natychmiast, gdy Pages dostanie świeży plik.

## Uwaga o zakresach

Ten rebuild celowo przywraca najpierw sprawdzony parser z działającej wersji.
Nie udaje, że skanuje wszystkie możliwe rynki, jeśli źródło ich nie wystawia w
odczytywanym widoku. Po ustabilizowaniu działania na GitHubie można rozbudować
parser o kolejne rynki bez ponownego zmieniania wyglądu strony.

## Testy

`pytest -q`

W przygotowanej paczce testy parsera i matematyki przechodzą.
