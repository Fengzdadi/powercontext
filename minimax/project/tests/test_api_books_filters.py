"""GET /books 的可借状态筛选（CAT-007）和出版年份区间筛选（CAT-008）。

这两个条目在 specs/catalog.md 中是“待实现”，本文件是它们的验收测试。
"""

import pytest

from conftest import ids

# 种子数据中有在架副本的图书，以及没有在架副本的图书（含没有任何副本的 B013）
AVAILABLE = ["B001", "B003", "B005", "B006", "B008", "B010", "B011", "B014", "B016"]
UNAVAILABLE = ["B002", "B004", "B007", "B009", "B012", "B013", "B015"]


def assert_invalid(response, field):
    assert response.status == 400
    assert response.json["error"]["code"] == "invalid_parameter"
    assert response.json["error"]["field"] == field


@pytest.mark.spec("CAT-007", "DATA-001")
def test_available_true_returns_only_books_with_copies_on_shelf(client):
    response = client.get("/books?available=true&page_size=50")
    assert response.status == 200
    assert ids(response) == AVAILABLE
    assert response.json["total"] == len(AVAILABLE)
    assert all(item["copies_available"] > 0 for item in response.json["items"])


@pytest.mark.spec("CAT-007", "DATA-001")
def test_available_false_returns_only_books_without_copies_on_shelf(client):
    response = client.get("/books?available=false&page_size=50")
    assert response.status == 200
    assert ids(response) == UNAVAILABLE
    assert response.json["total"] == len(UNAVAILABLE)
    assert all(item["copies_available"] == 0 for item in response.json["items"])


@pytest.mark.spec("CAT-007", "API-003")
@pytest.mark.parametrize("raw", ["TRUE", "True", "1", "%20true%20"])
def test_available_accepts_true_spellings(client, raw):
    assert ids(client.get(f"/books?available={raw}&page_size=50")) == AVAILABLE


@pytest.mark.spec("CAT-007", "API-003")
@pytest.mark.parametrize("raw", ["FALSE", "0"])
def test_available_accepts_false_spellings(client, raw):
    assert ids(client.get(f"/books?available={raw}&page_size=50")) == UNAVAILABLE


@pytest.mark.spec("CAT-007", "API-002", "API-003")
@pytest.mark.parametrize("raw", ["yes", "", "2", "on"])
def test_invalid_available_value_is_rejected(client, raw):
    assert_invalid(client.get(f"/books?available={raw}"), "available")


@pytest.mark.spec("CAT-008")
def test_year_range_is_inclusive(client):
    response = client.get("/books?year_from=2000&year_to=2015&page_size=50")
    assert response.status == 200
    assert ids(response) == ["B002", "B003", "B009", "B012", "B014", "B016"]


@pytest.mark.spec("CAT-008")
def test_single_year_range(client):
    assert ids(client.get("/books?year_from=2015&year_to=2015")) == ["B002", "B016"]


@pytest.mark.spec("CAT-008")
def test_year_from_alone(client):
    assert ids(client.get("/books?year_from=2016")) == ["B001", "B004"]


@pytest.mark.spec("CAT-008")
def test_year_to_alone(client):
    assert ids(client.get("/books?year_to=1950")) == ["B006", "B007"]


@pytest.mark.spec("CAT-008", "API-002", "API-004")
@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("year_from=abc", "year_from"),
        ("year_from=2000.5", "year_from"),
        ("year_to=20x5", "year_to"),
        ("year_to=", "year_to"),
    ],
)
def test_non_integer_year_is_rejected(client, query, field):
    assert_invalid(client.get(f"/books?{query}"), field)


@pytest.mark.spec("CAT-008", "API-002")
def test_year_from_after_year_to_is_rejected(client):
    assert_invalid(client.get("/books?year_from=2020&year_to=2010"), "year_from")


@pytest.mark.spec("CAT-007", "CAT-008", "CAT-001", "CAT-002")
def test_filters_combine_with_keyword_and_category(client):
    assert ids(client.get("/books?available=true&category=cs")) == ["B001", "B003", "B005"]
    assert ids(client.get("/books?available=true&q=python")) == ["B001"]
    assert ids(client.get("/books?available=false&category=lit")) == ["B007", "B009"]
    assert ids(client.get("/books?available=true&year_from=2000&year_to=2015")) == ["B003", "B014", "B016"]


@pytest.mark.spec("CAT-007", "CAT-004")
def test_filters_apply_before_pagination(client):
    first = client.get("/books?available=true&page_size=4")
    assert first.json["total"] == 9
    assert ids(first) == ["B001", "B003", "B005", "B006"]
    last = client.get("/books?available=true&page_size=4&page=3")
    assert last.json["total"] == 9
    assert ids(last) == ["B016"]


@pytest.mark.spec("CAT-007", "CAT-003")
def test_filters_apply_before_sorting(client):
    response = client.get("/books?available=false&sort=-year&page_size=50")
    assert ids(response) == ["B004", "B002", "B012", "B009", "B015", "B013", "B007"]


@pytest.mark.spec("CAT-007", "DATA-001", "LOAN-001", "LOAN-004")
def test_available_filter_follows_loans_and_returns(client):
    loan = client.post("/loans", {"member_id": "M002", "copy_id": "C021"}).json["loan"]  # B016 唯一的副本
    assert "B016" not in ids(client.get("/books?available=true&page_size=50"))
    assert "B016" in ids(client.get("/books?available=false&page_size=50"))
    client.post(f"/loans/{loan['id']}/return")
    assert "B016" in ids(client.get("/books?available=true&page_size=50"))
