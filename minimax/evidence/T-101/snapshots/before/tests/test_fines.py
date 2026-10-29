"""逾期罚款测试。"""

from datetime import date

import pytest

from library.fines import overdue_fine_cents

DUE = date(2026, 10, 1)


@pytest.mark.spec("FINE-001")
@pytest.mark.parametrize("returned", [date(2026, 9, 20), date(2026, 10, 1)])
def test_no_fine_when_returned_on_time(returned):
    assert overdue_fine_cents(DUE, returned, 5000) == 0


@pytest.mark.spec("FINE-001", "FINE-003")
def test_fine_is_fifty_cents_per_day():
    fine = overdue_fine_cents(DUE, date(2026, 10, 6), 5000)
    assert fine == 250
    assert isinstance(fine, int)


@pytest.mark.spec("FINE-002")
def test_fine_is_capped_at_book_price():
    assert overdue_fine_cents(DUE, date(2027, 1, 9), 2300) == 2300  # 逾期 100 天


@pytest.mark.spec("FINE-002")
def test_fine_below_cap_is_not_changed():
    assert overdue_fine_cents(DUE, date(2026, 10, 4), 2300) == 150
