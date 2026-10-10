# Analiza sportowa i automatyczne wyniki

`sports_ai.py` działa na GitHub Actions po skanie kursów, także przy zamkniętej stronie. Publikuje wspólną historię w `web/data/ai-coupons.json`. Frontend pobiera ją z Pages i z bieżącej gałęzi repozytorium. Dane skanera kursów i wyniki sportowe mają osobne statusy.

## Uruchomienie modelu

1. Utwórz klucz w https://aistudio.google.com/api-keys w projekcie korzystającym z bezpłatnego poziomu Gemini API. Dostępność i limity zależą od konta: https://ai.google.dev/gemini-api/docs/pricing . Nie trzeba włączać płatnego rozliczania dla tej integracji.
2. GitHub → repozytorium `xlvlcl/arbi` → Settings → Secrets and variables → Actions → New repository secret.
3. Nazwa: `GEMINI_API_KEY`. Wartość: klucz Gemini. Nie umieszczaj klucza w plikach ani kodzie strony.
4. Kolejne uruchomienie skanera wykryje sekret. Domyślny model: `gemini-3.5-flash-lite`. Bez sekretu widoczny jest stan `not_configured` i nie są tworzone pozorne analizy.

Model otrzymuje wyłącznie dane historycznych meczów: maksymalnie 12 dla każdej drużyny, minimum 6, nazwy rywali, daty i gole. Nie otrzymuje kursów, bookmakerów ani procentów z rynku. Jedno wywołanie obsługuje najwyżej sześć meczów; najwyżej jedna próba na godzinę. Błąd lub wyczerpanie limitu nie uruchamiają innego, płatnego modelu. Jeśli projekt Google ma włączony billing, obowiązuje konfiguracja tego projektu — kod nie przełącza jego planu.

Procenty są subiektywnymi ocenami LLM, bez historycznej kalibracji. Nie należy prezentować ich jako potwierdzonej skuteczności. Szansa AKO to iloczyn ocen przy założeniu niezależności. Kurs jest dołączany dopiero do gotowych typów, w celu złożenia kuponu 2–15 z preferencją 3–6. Kupon łączy maksymalnie trzy różne wydarzenia u jednego bukmachera. Dostępność takiego AKO należy sprawdzić u bukmachera.

## Zakres i wyniki

Źródło: [OpenLigaDB](https://www.openligadb.de/), dane na [licencji ODbL](https://www.openligadb.de/lizenz). Obsługiwane ligi: `bl1`, `bl2`, `bl3` (niemieckie ligi 1–3), sezon bieżący i poprzedni. Źródło jest społecznościowe i może mieć opóźnienia lub korekty. Nie pobieramy Flashscore.

Obsługiwane rynki dotyczą regulaminowego czasu: 1X2, sumy goli 1.5/2.5/3.5 oraz obie drużyny strzelą. Skaner dopasowuje drużyny i termin, a odrzuca niejednoznaczne pary. Rozliczenie używa jednoznacznego końcowego wyniku `resultTypeID=2`, typu `After90Minutes` (lub starszego formatu bez tego pola) oraz `matchIsFinished=true`. Nie używa wyniku do przerwy, dogrywki ani rzutu karnego jako osobnej bramki końcowego wyniku. Nieznany wynik pozostawia typ oczekujący. Niepowodzenie źródła nie tworzy porażki. Korekty wyników zapisują historię zmian.

To rozliczenie trafności sportowej typów, nie potwierdzenie wypłaty na koncie bukmachera. Nie obsługujemy walkowerów/anulowania kuponu, cash-outów, zwrotów częściowych ani rynków o niestandardowych zasadach. Nie tworzymy typów na kartki, rożne i faule: brak danych do analizy i rozliczenia. Brak również składów, kontuzji, sędziów i pogody. Model musi ujawniać te braki.

Stare kupony lokalne i ręczne wyniki nie są zaliczane do nowej historii serwerowej; można je wyeksportować w szczegółach zakładki. Maksymalnie 1000 kuponów w archiwum; po osiągnięciu limitu generator przestaje dodawać nowe, zachowując istniejące zapisy i ich rozliczanie.

## Testy

`python -m unittest discover -s fresh/tests -p test_sports_ai.py -v`

Testy obejmują brak kursów w wejściu modelu, walidację odwołań do historii, brak klucza, awarie źródła, dopasowanie meczu, AKO i brak duplikatów, wynik końcowy, oczekiwanie i korekty rozliczeń. Wywołania AI w testach są symulowane. Rzeczywista odpowiedź modelu wymaga poprawnego sekretu i uprawnień dostawcy.
