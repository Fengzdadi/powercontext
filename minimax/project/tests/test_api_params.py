"""查询参数解析的单元测试。"""

import pytest

from library.api.app import parse_query
from library.api.params import parse_bool, parse_choice, parse_int
from library.errors import InvalidParameter

pytestmark = pytest.mark.spec("API-003", "API-004")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("TRUE", True), (" True ", True), ("1", True), ("false", False), ("False", False), ("0", False)],
)
def test_parse_bool_accepts_documented_spellings(raw, expected):
    assert parse_bool({"flag": raw}, "flag") is expected


@pytest.mark.parametrize("raw", ["yes", "no", "", "2", "t"])
def test_parse_bool_rejects_other_values(raw):
    with pytest.raises(InvalidParameter) as exc:
        parse_bool({"flag": raw}, "flag")
    assert exc.value.field == "flag"


def test_parse_bool_missing_returns_none():
    assert parse_bool({}, "flag") is None


@pytest.mark.parametrize(("raw", "expected"), [("7", 7), (" 7 ", 7), ("+3", 3), ("-2", -2), ("0010", 10)])
def test_parse_int_accepts_decimal_integers(raw, expected):
    assert parse_int({"n": raw}, "n") == expected


@pytest.mark.parametrize("raw", ["abc", "1.5", "1_000", "", "١٢", "1e3"])
def test_parse_int_rejects_non_integers(raw):
    with pytest.raises(InvalidParameter) as exc:
        parse_int({"n": raw}, "n")
    assert exc.value.field == "n"


def test_parse_int_range_and_default():
    assert parse_int({}, "n", default=5) == 5
    with pytest.raises(InvalidParameter):
        parse_int({"n": "0"}, "n", minimum=1)
    with pytest.raises(InvalidParameter):
        parse_int({"n": "51"}, "n", maximum=50)


@pytest.mark.spec("API-002")
def test_parse_choice():
    assert parse_choice({}, "sort", ["id", "year"], default="id") == "id"
    assert parse_choice({"sort": "year"}, "sort", ["id", "year"], default="id") == "year"
    with pytest.raises(InvalidParameter) as exc:
        parse_choice({"sort": "price"}, "sort", ["id", "year"], default="id")
    assert exc.value.field == "sort"


@pytest.mark.spec("API-005")
def test_parse_query_keeps_first_value_and_blank_values():
    assert parse_query("a=1&a=2&b=&c=x+y") == {"a": "1", "b": "", "c": "x y"}
