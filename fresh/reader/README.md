# Czytnik kursów poza GitHub

GitHub Actions dostaje od DobryBuk HTTP 403 na runnerach Ubuntu, Windows i macOS. Odczyt przez ten Worker został potwierdzony 8 października 2026: katalog 1575 wydarzeń, 40 pełnych odczytów szczegółów i poprawne regularne skany. Dostępność źródła może zmienić się w przyszłości.

Odczyt źródła obsługuje tylko publiczne endpointy DobryBuk, tylko GET, i wymaga tokenu. Worker nie rozwiązuje wyzwań Cloudflare ani nie odtwarza cookies. Po podłączeniu KV przechowuje jeden ostatni wynik skanera dla panelu. Skaner, obliczenia, Telegram i OneSignal pozostają w GitHub Actions. Komputer użytkownika nie musi działać.

## Jednorazowe podłączenie

1. Wejdź na https://dash.cloudflare.com/ i utwórz konto Free. Workers oferuje start bez karty: https://www.cloudflare.com/products/workers/ .
2. Workers & Pages → Create application → Import a repository → GitHub → `xlvlcl/arbi`.
3. Nazwa Workera: `arbi`; katalog główny (Root directory): `fresh/reader`; komenda budowania pusta; komenda wdrożenia `npx wrangler deploy`.
4. Po wdrożeniu: Worker → Settings → Variables and Secrets → Add → typ **Secret**, nazwa `READER_TOKEN`. Ustaw własny losowy token co najmniej 32 znaków. Nie wklejaj go do rozmowy ani kodu. Kliknij Deploy.
5. Otwórz adres `https://arbi.<twoja-subdomena>.workers.dev/`. Powinien pokazać `configured: true`. To potwierdza konfigurację, **nie dostęp do kursów**.
6. W https://github.com/xlvlcl/arbi/settings/secrets/actions dodaj dwa Repository secrets:
   - `SOURCE_READER_URL`: powyższy URL bez dalszej ścieżki.
   - `SOURCE_READER_TOKEN`: identyczny token jak `READER_TOKEN` w Cloudflare.
7. W https://github.com/xlvlcl/arbi/actions/workflows/surebet.yml kliknij Run workflow (publish zostaw wyłączone). Następne regularne skany też użyją czytnika.

## Potwierdzenie wyniku

Odczyt jest potwierdzony dopiero wtedy, gdy log skanera pokazuje pobrane wydarzenia i `fresh/web/data/latest.json` zawiera świeży `last_success_at`. Zero surebetów może być poprawnym wynikiem. HTTP 403 oznacza, że źródło blokuje także Cloudflare — wtedy potrzebne będzie uzgodnione z dostawcą API lub inne źródło danych.

## Wynik dla panelu przez KV

Panel może czytać `/feed/latest` bez czekania na aktualizację pliku w Pages lub cache raw.githubusercontent.com. To publiczny wynik tego samego skanera; dane były już publiczne w repozytorium. Zapis PUT wymaga istniejącego tokenu i wykonuje go wyłącznie skaner. Powiadomienia pozostają niezależne od panelu.

1. Worker → Settings → Builds → Build watch paths: Include `fresh/reader/*`, zamiast `*`. To zapobiega wdrożeniu Workera przy każdym zapisie kursów.
2. Storage & databases → KV → Create namespace: `arbi-data`.
3. Worker `arbi` → Settings → Bindings → Add binding → KV Namespace. Variable name: **`DATA`**; namespace: **`arbi-data`**. Zapisz/wdróż.
4. Dodaj ID namespace (publiczny identyfikator, nie sekret) do `fresh/reader/wrangler.jsonc`, by kolejne wdrożenia zachowały binding:

```json
"kv_namespaces": [{"binding": "DATA", "id": "ID_UTWORZONEGO_NAMESPACE"}]
```

Nie dodawaj fikcyjnego ID. Do czasu utworzenia namespace i zapisania prawdziwego ID opcjonalna publikacja zwraca ostrzeżenie 503 i panel używa GitHub. To nie blokuje skanów ani alertów.

Po podłączeniu root Workera pokaże `feed_configured: true`. Następny regularny skan zapisze wynik. `/feed/latest` powinien pokazać JSON ze świeżym `status.attempt_at`. Publikacja zapisuje najwyżej jeden wynik na 90 sekund (typowo co 2 minuty); ten limit ogranicza zużycie KV. Nieudany zapis nie blokuje ponownej próby. Katalog w wyniku dla panelu zawiera tylko kursy 1/X/2 widoczne w kartach, natomiast skaner i wszystkie wyniki Surebet/Radar/Valuebet zachowują pełne obliczenia i rynki.

KV ma opóźnienie propagacji między lokalizacjami, zwykle do 60 sekund; ustawiamy `cacheTtl: 30` oraz `Cache-Control: no-store` i ETag. Strona kontroluje wiek kursów i próbuje zapasowego odczytu, gdy wynik jest stary. Ta zmiana nie gwarantuje bezprzerwowego działania źródła, harmonogramu Actions ani doręczenia powiadomień.

Worker Free: 100 000 żądań/dzień, 10 ms CPU na żądanie. Worker przesyła odpowiedzi strumieniowo, bez przeliczania lub parsowania katalogu. Docelowy skaner nadal działa zgodnie z harmonogramem Actions; to rozwiązanie nie dodaje nowego harmonogramu. Przetestuj limity i źródło na wdrożonym Workerze przed uznaniem integracji za działającą.

Wyłączenie czytnika: usuń sekret `SOURCE_READER_URL` w GitHub; skaner wróci do bezpośredniego źródła. Nie ujawniaj tokenu w URL lub publicznych plikach.

Dokumentacja: https://developers.cloudflare.com/workers/get-started/dashboard/ , https://developers.cloudflare.com/workers/configuration/secrets/ , https://developers.cloudflare.com/workers/platform/limits/ .
