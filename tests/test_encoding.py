"""Encoding tests.

The indexed-bracket form is the whole reason this module exists: sending
``pm=twint`` or ``pm[]=twint`` makes Payrexx answer ``200 OK`` and silently drop the
filter, so a regression here would be invisible in production until a shopper paid
by an unexpected method.
"""

from payrexx.encoding import encode_form


def test_scalars_pass_through():
    assert encode_form({"amount": 1500, "currency": "CHF"}) == [
        ("amount", "1500"),
        ("currency", "CHF"),
    ]


def test_list_uses_numeric_indices_not_empty_brackets():
    # The single most important assertion in this suite.
    assert encode_form({"pm": ["twint", "visa"]}) == [
        ("pm[0]", "twint"),
        ("pm[1]", "visa"),
    ]


def test_nested_mapping_uses_bracket_path():
    assert encode_form({"fields": {"forename": {"value": "Jean"}}}) == [
        ("fields[forename][value]", "Jean")
    ]


def test_booleans_become_one_and_zero():
    assert encode_form({"printSlip": True, "reservation": False}) == [
        ("printSlip", "1"),
        ("reservation", "0"),
    ]


def test_none_is_omitted_not_sent_empty():
    # An empty string is a real value to Payrexx and would blank stored fields.
    assert encode_form({"amount": 100, "purpose": None}) == [("amount", "100")]


def test_integral_float_does_not_grow_a_decimal_point():
    assert encode_form({"amount": 1500.0}) == [("amount", "1500")]


def test_strings_are_not_treated_as_sequences():
    assert encode_form({"currency": "CHF"}) == [("currency", "CHF")]


def test_list_of_mappings_nests_correctly():
    assert encode_form({"shopItems": [{"name": "Beer", "price": 10}]}) == [
        ("shopItems[0][name]", "Beer"),
        ("shopItems[0][price]", "10"),
    ]


def test_key_order_is_preserved():
    pairs = encode_form({"z": 1, "a": 2, "m": 3})
    assert [k for k, _ in pairs] == ["z", "a", "m"]
