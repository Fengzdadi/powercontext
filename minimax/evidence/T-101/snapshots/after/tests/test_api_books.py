"""GET /books 与 GET /books/{book_id} 的接口测试。"""

import pytest

from conftest import ids


@pytest.mark.spec("API-001")
def test_responses_are_json(client):
    response = client.get("/books")
    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"


@pytest.mark.spec("API-001", "API-002")
def test_unknown_route_returns_not_found(client):
    response = client.get("/authors")
    assert response.status == 404
    assert response.json["error"]["code"] == "not_found"


@pytest.mark.spec("CAT-004")
def test_default_listing_shape(client):
    response = client.get("/books")
    assert response.status == 200
    assert response.json["total"] == 16
    assert response.json["page"] == 1
    assert response.json["page_size"] == 10
    assert ids(response) == [f"B{i:03d}" for i in range(1, 11)]


@pytest.mark.spec("CAT-001")
def test_keyword_query(client):
    assert ids(client.get("/books?q=python")) == ["B001", "B002"]
    assert client.get("/books?q=%20%20").json["total"] == 16


@pytest.mark.spec("CAT-002", "API-002")
def test_category_query_and_unknown_category(client):
    assert ids(client.get("/books?category=hist")) == ["B011", "B012", "B013"]
    response = client.get("/books?category=music")
    assert response.status == 400
    assert response.json["error"] == {
        "code": "invalid_parameter",
        "message": response.json["error"]["message"],
        "field": "category",
    }


@pytest.mark.spec("CAT-003", "API-002")
def test_sort_query(client):
    assert ids(client.get("/books?sort=-year&page_size=3")) == ["B004", "B001", "B002"]
    response = client.get("/books?sort=price")
    assert response.status == 400
    assert response.json["error"]["field"] == "sort"


@pytest.mark.spec("CAT-004", "API-002", "API-004")
@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("page=0", "page"),
        ("page=-1", "page"),
        ("page=abc", "page"),
        ("page_size=0", "page_size"),
        ("page_size=51", "page_size"),
        ("page_size=1.5", "page_size"),
    ],
)
def test_invalid_pagination_parameters(client, query, field):
    response = client.get(f"/books?{query}")
    assert response.status == 400
    assert response.json["error"]["code"] == "invalid_parameter"
    assert response.json["error"]["field"] == field


@pytest.mark.spec("CAT-004")
def test_last_page(client):
    response = client.get("/books?page=2&page_size=10")
    assert response.json["total"] == 16
    assert ids(response) == [f"B{i:03d}" for i in range(11, 17)]


@pytest.mark.spec("API-005")
def test_unknown_query_parameters_are_ignored(client):
    assert client.get("/books?foo=bar").json == client.get("/books").json


@pytest.mark.spec("API-005", "CAT-002")
def test_repeated_parameter_uses_first_value(client):
    assert ids(client.get("/books?category=hist&category=cs")) == ["B011", "B012", "B013"]


@pytest.mark.spec("CAT-005", "DATA-001")
def test_book_detail(client):
    response = client.get("/books/B002")
    assert response.status == 200
    assert response.json["copies_total"] == 2
    assert response.json["copies_available"] == 0
    assert [copy["status"] for copy in response.json["copies"]] == ["on_loan", "on_loan"]


@pytest.mark.spec("CAT-005", "DATA-001")
def test_book_detail_counts_only_on_shelf_copies(client):
    response = client.get("/books/B006")
    assert response.json["copies_total"] == 2
    assert response.json["copies_available"] == 1


@pytest.mark.spec("CAT-005", "API-002")
def test_missing_book_returns_not_found(client):
    response = client.get("/books/B999")
    assert response.status == 404
    assert response.json["error"] == {
        "code": "not_found",
        "message": response.json["error"]["message"],
        "field": None,
    }


@pytest.mark.spec("DATA-002")
def test_seed_books_use_integer_year_and_price(repo):
    for book in repo.books.values():
        assert isinstance(book.year, int)
        assert isinstance(book.price_cents, int)
