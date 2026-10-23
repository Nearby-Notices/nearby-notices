from inspect_quote_check import decide, numbers

SOURCE = ("The Council intends to prohibit waiting from a point 35m south east of the junction of Ednam Road "
          "to a point 68m south east of the junction with Ednam Road. Objections by 20 May 2025.")


def test_kept_when_grounded():
    kept, _, reason = decide(SOURCE, '{"supported": true, "quotes": ["a point 68m south east of the junction with Ednam Road"]}',
                             "Waiting is prohibited up to 68m south east of the junction.")
    assert kept, reason


def test_removed_when_a_number_is_not_in_the_quotes():
    kept, _, reason = decide(SOURCE, '{"supported": true, "quotes": ["a point 68m south east of the junction with Ednam Road"]}',
                             "Waiting is prohibited up to 75m south east of the junction.")
    assert not kept and reason.startswith("number not in quotes")


def test_removed_when_a_quote_is_invented():
    kept, _, reason = decide(SOURCE, '{"supported": true, "quotes": ["objections by 30 May 2025"]}', "")
    assert not kept and reason.startswith("quote not in source")


def test_removed_when_unsupported_or_unreadable():
    assert not decide(SOURCE, '{"supported": false, "quotes": ["Ednam Road"]}')[0]
    assert not decide(SOURCE, "not json")[0]


def test_ellipsis_spans_each_checked():
    kept, _, _ = decide(SOURCE, '{"supported": true, "quotes": ["The Council intends ... Objections by 20 May 2025"]}', "")
    assert kept


def test_numbers():
    assert numbers("1,000 homes by 9th October 2026, 4.3 hours") == {"1000", "9", "2026", "4.3"}
