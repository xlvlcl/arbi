# Surebet Alert v12

Ta wersja zachowuje obecny ciemny interfejs i dodaje dwie kluczowe zmiany:

1. **Sporty są wykrywane dynamicznie** z sekcji `Sporty` na stronie porównywarki, zamiast polegać tylko na stałej liście.
2. **Dane strony odświeżają się bez czekania na deployment Pages** — skaner zapisuje `docs/data/latest.json` do gałęzi `main`, a frontend odpytuje ten plik co 3 sekundy.

GitHubowy `schedule` co 5 minut zostaje jako backup. Do regularnego uruchamiania użyj zewnętrznego wyzwalacza zgodnie z `SCHEDULER_CRONJOB_ORG.txt`.

## Zakres

Skaner odwiedza wydarzenia znalezione w publicznej porównywarce, następnie otwiera strony wydarzeń i analizuje widoczne rynki. Niepełne rynki nie są uznawane za arbitraż.

Nie można zagwarantować pokrycia sportów lub rynków, których źródło DobryBuk nie udostępnia.
