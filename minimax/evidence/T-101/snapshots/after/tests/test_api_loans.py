"""借还接口测试。"""

import pytest


@pytest.mark.spec("LOAN-001", "LOAN-003", "API-001")
def test_create_loan(client):
    response = client.post("/loans", {"member_id": "M002", "copy_id": "C001"})
    assert response.status == 201
    assert response.json["loan"]["due_on"] == "2026-11-14"
    assert client.get("/books/B001").json["copies_available"] == 0


@pytest.mark.spec("LOAN-001", "API-002")
@pytest.mark.parametrize(
    ("body", "field"),
    [(None, "member_id"), ({"member_id": "M001"}, "copy_id"), ({"member_id": " ", "copy_id": "C001"}, "member_id")],
)
def test_create_loan_validates_body(client, body, field):
    response = client.post("/loans", body)
    assert response.status == 400
    assert response.json["error"]["code"] == "invalid_parameter"
    assert response.json["error"]["field"] == field


@pytest.mark.spec("LOAN-001", "API-002")
def test_rule_violations_use_specific_codes(client):
    response = client.post("/loans", {"member_id": "M004", "copy_id": "C001"})
    assert response.status == 409
    assert response.json["error"]["code"] == "member_inactive"
    assert response.json["error"]["field"] is None


@pytest.mark.spec("LOAN-004", "FINE-001", "FINE-003")
def test_return_reports_fine(client):
    response = client.post("/loans/L002/return")
    assert response.status == 200
    assert response.json["fine_cents"] == 700
    assert response.json["loan"]["returned_on"] == "2026-10-15"


@pytest.mark.spec("LOAN-004", "API-002")
def test_return_unknown_loan(client):
    response = client.post("/loans/L999/return")
    assert response.status == 404
    assert response.json["error"]["code"] == "not_found"


@pytest.mark.spec("LOAN-005")
def test_renew_loan(client):
    response = client.post("/loans/L001/renew")
    assert response.status == 200
    assert response.json["loan"]["due_on"] == "2026-11-19"
    assert client.post("/loans/L002/renew").json["error"]["code"] == "loan_overdue"


@pytest.mark.spec("LOAN-006", "API-003")
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", ["L004", "L001"]),
        ("?include_returned=false", ["L004", "L001"]),
        ("?include_returned=1", ["L004", "L001", "L008"]),
        ("?include_returned=True", ["L004", "L001", "L008"]),
    ],
)
def test_member_loans(client, query, expected):
    response = client.get(f"/members/M001/loans{query}")
    assert response.status == 200
    assert [item["id"] for item in response.json["items"]] == expected


@pytest.mark.spec("LOAN-006", "API-003", "API-002")
def test_member_loans_rejects_invalid_boolean(client):
    response = client.get("/members/M001/loans?include_returned=maybe")
    assert response.status == 400
    assert response.json["error"]["field"] == "include_returned"
    assert client.get("/members/M999/loans").status == 404
