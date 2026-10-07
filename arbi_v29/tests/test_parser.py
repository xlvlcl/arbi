from app.providers.dobrybuk import discover_events_from_html, discover_sports_from_text, extract_detail_market, odds_from_text


def test_discover_all_event_links_from_listing():
    html = '''
    <table>
      <tr><th>Godzina</th><th>Zdarzenie</th><th>Bonusy</th><th>1</th><th>X</th><th>2</th></tr>
      <tr><td>20:00</td><td><a href="/kursy/mecz/a-vs-b-123">A-B</a></td><td></td><td>2.10</td><td>3.20</td><td>3.50</td></tr>
      <tr><td>21:00</td><td><a href="/kursy/mecz/c-vs-d-456">C-D</a></td><td></td><td>1.90</td><td>3.50</td><td>4.10</td></tr>
    </table>
    '''
    rows = discover_events_from_html(html, "Piłka nożna", "https://dobrybuk.pl/kursy")
    assert len(rows) == 2
    assert rows[0]["event"] == "A-B"
    assert rows[1]["event_url"].endswith("/kursy/mecz/c-vs-d-456")


def test_detail_table_keeps_all_bookmakers_and_ignores_percentages():
    html = '''
    <table>
      <tr><th>Bukmacher</th><th>Tak</th><th>Nie</th></tr>
      <tr><td><a href="https://betclic.pl">Betclic</a></td><td>2.10 47.1%</td><td>1.75 52.9%</td></tr>
      <tr><td><a href="https://efortuna.pl">Fortuna</a></td><td>2.05 48.0%</td><td>2.15 52.0%</td></tr>
      <tr><td><a href="https://sts.pl">STS</a></td><td>2.00</td><td>2.05</td></tr>
    </table>
    '''
    market = extract_detail_market(html, "A-B", "Piłka nożna", "Zawodnik strzeli gola", "https://dobrybuk.pl/mecz")
    assert market is not None
    assert len(market["quotes"]["Tak"]) == 3
    assert len(market["quotes"]["Nie"]) == 3
    assert market["quotes"]["Nie"][0]["bookmaker"] == "Fortuna"
    assert market["quotes"]["Nie"][0]["odds"] == 2.15
    assert odds_from_text("4.40 21.1%") == [4.40]


def test_dynamic_sport_discovery_from_page_text():
    text = """
    Porównywarka kursów
    Sporty
    ⚽ Piłka nożna
    🎾 Tenis
    🏀 Koszykówka
    🏐 Siatkówka
    🎯 Dart
    Status zdarzeń
    Nadchodzące
    """
    assert discover_sports_from_text(text) == [
        "Piłka nożna",
        "Tenis",
        "Koszykówka",
        "Siatkówka",
        "Dart",
    ]
