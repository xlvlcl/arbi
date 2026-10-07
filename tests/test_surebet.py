import time

from app.models import Quote
from app.surebet import allocation, detect


def q(selection, bookmaker, odds):
    return Quote(selection, odds, bookmaker, time.time(), "https://event", f"https://{bookmaker}.example")


def test_basic_binary_yes_no_arb_and_alternatives():
    quotes = {
        "Tak": [q("Tak", "Betclic", 2.10), q("Tak", "STS", 2.02)],
        "Nie": [q("Nie", "Fortuna", 2.10), q("Nie", "LVBet", 2.01)],
    }
    arbs = detect(
        "A-B",
        "Piłka nożna",
        "Zawodnik strzeli gola",
        quotes,
        100,
        {"Betclic": 1.0, "Fortuna": 1.0, "STS": 1.0, "LVBet": 1.0},
        0.0,
        180,
    )
    assert len(arbs) == 1
    assert arbs[0].profit_pct > 4.0
    assert arbs[0].legs[0].alternatives


def test_185_yes_no_is_not_an_arb():
    quotes = {"Tak": [q("Tak", "Betclic", 1.85)], "Nie": [q("Nie", "Fortuna", 1.85)]}
    assert detect("A-B", "Piłka nożna", "Czy strzeli gola?", quotes, 100, {"Betclic": 1, "Fortuna": 1}, 0, 180) == []


def test_incomplete_1x2_x_and_2_is_rejected():
    quotes = {
        "X": [q("X", "LVBet", 3.65)],
        "2": [q("2", "LVBet", 5.20)],
    }
    assert detect("Egipt-RPA", "Piłka nożna", "1X2", quotes, 100, {"LVBet": 1.0}, 0, 180) == []


def test_full_1x2_works_when_mathematically_profitable():
    quotes = {
        "1": [q("1", "A", 3.40)],
        "X": [q("X", "B", 3.60)],
        "2": [q("2", "C", 3.50)],
    }
    arbs = detect("A-B", "Piłka nożna", "1X2", quotes, 100, {"A": 1, "B": 1, "C": 1}, 0, 180)
    assert arbs


def test_over_under_same_line_works():
    quotes = {"U 2.5": [q("U 2.5", "A", 2.10)], "O 2.5": [q("O 2.5", "B", 2.10)]}
    assert detect("A-B", "Piłka nożna", "U/O 2.5", quotes, 100, {"A": 1, "B": 1}, 0, 180)


def test_double_chance_is_rejected():
    quotes = {
        "1X": [q("1X", "A", 2.10)],
        "X2": [q("X2", "B", 2.10)],
        "12": [q("12", "C", 2.10)],
    }
    assert detect("A-B", "Piłka nożna", "1X / X2 / 12", quotes, 100, {"A": 1, "B": 1, "C": 1}, 0, 180) == []


def test_tax_can_kill_small_edge():
    qs = [q("A", "Superbet", 2.10), q("B", "STS", 2.10)]
    assert allocation(qs, 50, {"Superbet": 0.88, "STS": 0.88}) is None


def test_same_bookmaker_false_arb_is_rejected():
    quotes = {
        "1": [q("1", "TotalBet", 20.0)],
        "2": [q("2", "TotalBet", 20.0)],
    }
    assert detect(
        "A-B", "Tenis", "Winner", quotes, 100,
        {"TotalBet": 1.0}, 0, 180,
    ) == []


def test_absurd_cross_book_profit_is_rejected_as_parser_outlier():
    quotes = {
        "1": [q("1", "Betclic", 10.0)],
        "2": [q("2", "Fortuna", 10.0)],
    }
    assert detect(
        "A-B", "Tenis", "Winner", quotes, 100,
        {"Betclic": 1.0, "Fortuna": 1.0}, 0, 180,
    ) == []


def test_same_book_best_prices_can_rescue_with_second_book_quote():
    quotes = {
        "1": [q("1", "A", 2.20), q("1", "B", 2.15)],
        "2": [q("2", "A", 2.20), q("2", "C", 2.15)],
    }
    arbs = detect(
        "A-B", "Tenis", "Winner", quotes, 100,
        {"A": 1.0, "B": 1.0, "C": 1.0}, 0, 180,
    )
    assert arbs
    assert len({leg.bookmaker for leg in arbs[0].legs}) >= 2
