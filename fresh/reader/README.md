# Czytnik kursów poza GitHub

GitHub Actions dostaje od DobryBuk HTTP 403 na runnerach Ubuntu, Windows i macOS. Ten moduł pozwala sprawdzić odczyt z Cloudflare Workers. **Nie został jeszcze sprawdzony na hostingu Cloudflare. Może tam wystąpić ta sama blokada.**

Worker obsługuje tylko publiczne endpointy DobryBuk, tylko GET, i wymaga tokenu. Nie rozwiązuje wyzwań Cloudflare ani nie odtwarza cookies. Nie przechowuje kursów. Skaner, obliczenia, Telegram i OneSignal pozostają w GitHub Actions. Komputer użytkownika nie musi działać.

## Jednorazowe podłączenie

1. Wejdź na https://dash.cloudflare.com/ i utwórz konto Free. Workers oferuje start bez karty: https://www.cloudflare.com/products/workers/ .
2. Workers & Pages → Create application → Import a repository → GitHub → `xlvlcl/arbi`.
3. Nazwa Workera: `arbi-source-reader`; katalog główny (Root directory): `fresh/reader`; komenda budowania pusta; komenda wdrożenia `npx wrangler deploy`.
4. Po wdrożeniu: Worker → Settings → Variables and Secrets → Add → typ **Secret**, nazwa `READER_TOKEN`. Ustaw własny losowy token co najmniej 32 znaków. Nie wklejaj go do rozmowy ani kodu. Kliknij Deploy.
5. Otwórz adres `https://arbi-source-reader.<twoja-subdomena>.workers.dev/`. Powinien pokazać `configured: true`. To potwierdza konfigurację, **nie dostęp do kursów**.
6. W https://github.com/xlvlcl/arbi/settings/secrets/actions dodaj dwa Repository secrets:
   - `SOURCE_READER_URL`: powyższy URL bez dalszej ścieżki.
   - `SOURCE_READER_TOKEN`: identyczny token jak `READER_TOKEN` w Cloudflare.
7. W https://github.com/xlvlcl/arbi/actions/workflows/surebet.yml kliknij Run workflow (publish zostaw wyłączone). Następne regularne skany też użyją czytnika.

## Potwierdzenie wyniku

Odczyt jest potwierdzony dopiero wtedy, gdy log skanera pokazuje pobrane wydarzenia i `fresh/web/data/latest.json` zawiera świeży `last_success_at`. Zero surebetów może być poprawnym wynikiem. HTTP 403 oznacza, że źródło blokuje także Cloudflare — wtedy potrzebne będzie uzgodnione z dostawcą API lub inne źródło danych.

Worker Free: 100 000 żądań/dzień, 10 ms CPU na żądanie. Worker przesyła odpowiedzi strumieniowo, bez przeliczania lub parsowania katalogu. Docelowy skaner nadal działa zgodnie z harmonogramem Actions; to rozwiązanie nie dodaje nowego harmonogramu. Przetestuj limity i źródło na wdrożonym Workerze przed uznaniem integracji za działającą.

Wyłączenie czytnika: usuń sekret `SOURCE_READER_URL` w GitHub; skaner wróci do bezpośredniego źródła. Nie ujawniaj tokenu w URL lub publicznych plikach.

Dokumentacja: https://developers.cloudflare.com/workers/get-started/dashboard/ , https://developers.cloudflare.com/workers/configuration/secrets/ , https://developers.cloudflare.com/workers/platform/limits/ .
