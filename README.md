# Surebet Alert — przebudowana wersja

Najważniejsze zmiany:

- skaner nie używa już Playwrighta do zwykłego pobierania kursów;
- korzysta z HTTP + BeautifulSoup, dzięki czemu uruchomienie jest znacznie lżejsze;
- nie ma whitelisty 12 sportów jako głównego mechanizmu skanowania;
- zbiera linki do wydarzeń z publicznej porównywarki;
- dla wydarzeń odkrywa dostępne przyciski rynków i próbuje pobrać je przez parametr `market=...`;
- zachowuje kursy wielu bukmacherów dla tego samego wyniku;
- panel odświeża JSON co 5 sekund bez przeładowania strony;
- Telegram pozostaje konfigurowany przez GitHub Secrets.

## Ważne

GitHub Actions nadal nie jest serwerem czasu rzeczywistego. Harmonogram może zostać opóźniony przez GitHub. Ta wersja przede wszystkim skraca sam skan. Do częstszego wywoływania workflow można później dołożyć zewnętrzny darmowy scheduler.

## Uruchomienie lokalne

```bash
pip install -r requirements.txt
python scanner.py
```

Sekrety:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
