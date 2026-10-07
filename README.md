# Arbi v31 — API-first

v31 dodaje stabilne, udokumentowane źródła kursów jako warstwę priorytetową i zostawia
DobryBuk oraz publiczne strony bukmacherów wyłącznie jako fallback.

Obsługiwane feedy serwerowe:

- `ARBISCAN_API_KEY` — ArbiScan API (polskie marki; prematch),
- `ODDS_API_IO_KEY` — Odds-API.io (m.in. Betclic PL, eFortuna PL, STS PL, Superbet,
  Betfan PL, LVbet PL zależnie od planu/wybranych bukmacherów).

Nie trzeba konfigurować obu. Gdy żaden klucz nie istnieje, v31 nadal uruchamia stare
publiczne fallbacki, ale GitHub Actions może być przez strony bukmacherów blokowany.

## GitHub Secrets

Repo -> Settings -> Secrets and variables -> Actions -> New repository secret.

Dodaj co najmniej jeden:

- `ARBISCAN_API_KEY`
- `ODDS_API_IO_KEY`

Klucza nigdy nie wpisuj do `scanner.py`, `docs/` ani pliku YAML jako zwykły tekst.

## Bezpieczeństwo danych

v31 nie omija CAPTCHA, Cloudflare ani innych zabezpieczeń stron. Zamiast tego używa
udokumentowanych feedów. Surebet z API jest ponownie pobierany przed alertem; dane z
różnych bukmacherów są łączone po tym samym wydarzeniu i rynku, a stare kursy nie są
publikowane jako świeże.
