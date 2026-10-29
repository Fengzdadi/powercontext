"""借还服务层测试。"""

from datetime import date

import pytest

from conftest import TODAY
from library.errors import NotFound, RuleViolation
from library.loans import borrow, member_loans, renew, return_copy
from library.models import CopyStatus


@pytest.mark.spec("LOAN-001", "LOAN-003")
def test_borrow_creates_loan_and_marks_copy_on_loan(repo):
    loan = borrow(repo, "M002", "C001", TODAY)
    assert loan.id == "L010"
    assert loan.due_on == date(2026, 11, 14)
    assert repo.copies["C001"].status is CopyStatus.ON_LOAN


@pytest.mark.spec("LOAN-003")
def test_staff_loan_period_is_sixty_days(repo):
    assert borrow(repo, "M003", "C001", TODAY).due_on == date(2026, 12, 14)


@pytest.mark.spec("LOAN-001")
def test_inactive_member_cannot_borrow(repo):
    with pytest.raises(RuleViolation) as exc:
        borrow(repo, "M004", "C001", TODAY)
    assert exc.value.code == "member_inactive"


@pytest.mark.spec("LOAN-001", "DATA-001")
@pytest.mark.parametrize("copy_id", ["C002", "C006", "C009"])
def test_only_on_shelf_copies_can_be_borrowed(repo, copy_id):
    with pytest.raises(RuleViolation) as exc:
        borrow(repo, "M001", copy_id, TODAY)
    assert exc.value.code == "copy_unavailable"


@pytest.mark.spec("LOAN-001")
def test_unknown_member_or_copy(repo):
    with pytest.raises(NotFound):
        borrow(repo, "M999", "C001", TODAY)
    with pytest.raises(NotFound):
        borrow(repo, "M001", "C999", TODAY)


@pytest.mark.spec("LOAN-002")
def test_student_loan_limit_is_five(repo):
    for copy_id in ["C001", "C005", "C007", "C008"]:
        borrow(repo, "M005", copy_id, TODAY)
    assert len(repo.open_loans_of("M005")) == 5
    with pytest.raises(RuleViolation) as exc:
        borrow(repo, "M005", "C010", TODAY)
    assert exc.value.code == "loan_limit_reached"


@pytest.mark.spec("LOAN-002")
def test_staff_loan_limit_is_ten(repo):
    for copy_id in ["C001", "C005", "C007", "C008", "C010", "C012", "C015", "C016"]:
        borrow(repo, "M003", copy_id, TODAY)
    assert len(repo.open_loans_of("M003")) == 10
    with pytest.raises(RuleViolation) as exc:
        borrow(repo, "M003", "C018", TODAY)
    assert exc.value.code == "loan_limit_reached"


@pytest.mark.spec("LOAN-004", "DATA-001")
def test_return_on_time_restores_copy(repo):
    loan, fine = return_copy(repo, "L001", TODAY)
    assert loan.returned_on == TODAY
    assert fine == 0
    assert repo.copies["C002"].status is CopyStatus.ON_SHELF


@pytest.mark.spec("LOAN-004", "FINE-001")
def test_late_return_charges_fine(repo):
    _, fine = return_copy(repo, "L002", TODAY)  # 应还 2026-10-01，逾期 14 天
    assert fine == 700


@pytest.mark.spec("LOAN-004")
def test_double_return_is_rejected(repo):
    return_copy(repo, "L001", TODAY)
    with pytest.raises(RuleViolation) as exc:
        return_copy(repo, "L001", TODAY)
    assert exc.value.code == "already_returned"


@pytest.mark.spec("LOAN-005")
def test_renew_twice_then_limit(repo):
    assert renew(repo, "L001", TODAY).due_on == date(2026, 11, 19)
    loan = renew(repo, "L001", TODAY)
    assert (loan.due_on, loan.renewals) == (date(2026, 12, 19), 2)
    with pytest.raises(RuleViolation) as exc:
        renew(repo, "L001", TODAY)
    assert exc.value.code == "renewal_limit_reached"


@pytest.mark.spec("LOAN-005")
def test_overdue_or_returned_loans_cannot_be_renewed(repo):
    with pytest.raises(RuleViolation) as exc:
        renew(repo, "L002", TODAY)
    assert exc.value.code == "loan_overdue"
    with pytest.raises(RuleViolation) as exc:
        renew(repo, "L008", TODAY)
    assert exc.value.code == "already_returned"


@pytest.mark.spec("LOAN-006")
def test_member_loans_sorted_by_borrow_date(repo):
    assert [loan.id for loan in member_loans(repo, "M001")] == ["L004", "L001"]
    assert [loan.id for loan in member_loans(repo, "M001", include_returned=True)] == ["L004", "L001", "L008"]
    with pytest.raises(NotFound):
        member_loans(repo, "M999")
