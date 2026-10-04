from app.providers.dobrybuk import clean_event_name


def test_promotional_suffix_is_removed():
    raw = (
        "Znicz Pruszkow - Ruch Chorzów Puchar Polski · 28 paź, 16:00 "
        "RYNEK 1 KURS 3.30 ŚREDNIA 2.72 DO KUPONU · +21.4% IDŹ DO"
    )
    assert clean_event_name(raw) == (
        "Znicz Pruszkow - Ruch Chorzów Puchar Polski · 28 paź, 16:00"
    )


def test_normal_event_name_is_untouched():
    assert clean_event_name("Real Madrid - Barcelona") == "Real Madrid - Barcelona"
