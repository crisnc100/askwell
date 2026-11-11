from ledgerline.workspace import rules


def test_a_year_before_1000_is_stored_with_four_digits():
    # glibc's strftime("%Y") writes 999 for the year 999, and fromisoformat then refuses it.
    assert rules.convert("0999-01-01 00:00", "datetime") == "0999-01-01 00:00:00"
