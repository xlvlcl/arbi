from app.providers.dobrybuk import extract_listing_market, DobryBukProvider
from app.surebet import outcome_groups


def test_over_under_half_line_from_market_name():
    groups = outcome_groups("Piłka nożna", "U/O 2.5", ["U", "O"])
    assert groups == [["U", "O"]]


def test_integer_total_is_not_treated_as_simple_surebet():
    assert outcome_groups("Piłka nożna", "U/O 2.0", ["U 2.0", "O 2.0"]) == []


def test_quarter_total_is_not_treated_as_simple_surebet():
    assert outcome_groups("Piłka nożna", "U/O 2.25", ["U 2.25", "O 2.25"]) == []


def test_htft_complete_nine_way():
    labels = ["1/1","1/X","1/2","X/1","X/X","X/2","2/1","2/X","2/2"]
    assert outcome_groups("Piłka nożna", "HT/FT", labels) == [labels]


def test_set_score_best_of_three():
    labels = ["2-0","2-1","0-2","1-2"]
    assert outcome_groups("Tenis", "Wynik setów", labels) == [labels]


def test_correct_score_requires_other_bucket():
    labels = ["0-0","1-0","0-1","1-1","Inny wynik"]
    assert outcome_groups("Piłka nożna", "Dokładny wynik", labels) == [labels]


def test_first_team_to_score_requires_no_goal():
    labels = ["Drużyna 1","Drużyna 2","Brak gola"]
    assert outcome_groups("Piłka nożna", "Pierwsza drużyna strzeli", labels) == [labels]


def test_unknown_descriptive_market_label_is_allowed_structurally():
    provider = object.__new__(DobryBukProvider)
    assert provider._looks_like_market_label("Dokładny wynik")
    assert provider._looks_like_market_label("Rzuty rożne - gospodarze")
    assert provider._looks_like_market_label("Asy zawodnika")
    assert not provider._looks_like_market_label("1")
    assert not provider._looks_like_market_label("Zaloguj się")


def test_generic_listing_parser():
    html = """
    <table>
      <tr><th>Godzina</th><th>Zdarzenie</th><th>Bonusy</th><th>Tak</th><th>Nie</th></tr>
      <tr>
        <td>18:00</td>
        <td><a href="/kursy/mecz/a-vs-b-2026-10-05-1">A - B</a></td>
        <td></td>
        <td><img alt="STS"/>2.10</td>
        <td><img alt="Betclic"/>2.05</td>
      </tr>
    </table>
    """
    rows = extract_listing_market(html, "Piłka nożna", "Czy padnie gol?", "https://dobrybuk.pl/kursy")
    assert len(rows) == 1
    assert set(rows[0]["quotes"]) == {"Tak", "Nie"}
