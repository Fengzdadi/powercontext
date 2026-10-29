"""借阅、归还、续借和借阅记录。"""

from __future__ import annotations

from datetime import date, timedelta

from .errors import NotFound, RuleViolation
from .fines import overdue_fine_cents
from .models import CopyStatus, Loan
from .repository import Repository

MAX_RENEWALS = 2


def borrow(repo: Repository, member_id: str, copy_id: str, today: date) -> Loan:
    """借出一个副本。

    实现: LOAN-001, LOAN-002, LOAN-003
    """
    member = repo.members.get(member_id)
    if member is None:
        raise NotFound(f"读者 {member_id} 不存在")
    copy = repo.copies.get(copy_id)
    if copy is None:
        raise NotFound(f"副本 {copy_id} 不存在")
    if not member.active:
        raise RuleViolation("member_inactive", f"读者 {member_id} 的账户已停用")
    if copy.status is not CopyStatus.ON_SHELF:
        raise RuleViolation("copy_unavailable", f"副本 {copy_id} 当前不可借（{copy.status.value}）")
    if len(repo.open_loans_of(member_id)) >= member.kind.loan_limit:
        raise RuleViolation("loan_limit_reached", f"读者 {member_id} 已达到借阅上限 {member.kind.loan_limit} 本")

    loan = Loan(
        id=repo.next_loan_id(),
        copy_id=copy_id,
        member_id=member_id,
        borrowed_on=today,
        due_on=today + timedelta(days=member.kind.loan_days),
    )
    repo.loans[loan.id] = loan
    copy.status = CopyStatus.ON_LOAN
    return loan


def return_copy(repo: Repository, loan_id: str, today: date) -> tuple[Loan, int]:
    """归还并计算罚款，返回（借阅记录, 罚款分）。

    实现: LOAN-004
    """
    loan = repo.loans.get(loan_id)
    if loan is None:
        raise NotFound(f"借阅 {loan_id} 不存在")
    if not loan.is_open:
        raise RuleViolation("already_returned", f"借阅 {loan_id} 已经归还")
    copy = repo.copies[loan.copy_id]
    book = repo.books[copy.book_id]
    loan.returned_on = today
    copy.status = CopyStatus.ON_SHELF
    return loan, overdue_fine_cents(loan.due_on, today, book.price_cents)


def renew(repo: Repository, loan_id: str, today: date) -> Loan:
    """续借一个借期。

    实现: LOAN-005
    """
    loan = repo.loans.get(loan_id)
    if loan is None:
        raise NotFound(f"借阅 {loan_id} 不存在")
    if not loan.is_open:
        raise RuleViolation("already_returned", f"借阅 {loan_id} 已经归还")
    if today > loan.due_on:
        raise RuleViolation("loan_overdue", f"借阅 {loan_id} 已逾期，不能续借")
    if loan.renewals >= MAX_RENEWALS:
        raise RuleViolation("renewal_limit_reached", f"借阅 {loan_id} 已续借 {MAX_RENEWALS} 次")
    member = repo.members[loan.member_id]
    loan.due_on = loan.due_on + timedelta(days=member.kind.loan_days)
    loan.renewals += 1
    return loan


def member_loans(repo: Repository, member_id: str, include_returned: bool = False) -> list[Loan]:
    """读者的借阅记录，按借阅日期降序。

    实现: LOAN-006
    """
    if member_id not in repo.members:
        raise NotFound(f"读者 {member_id} 不存在")
    loans = repo.loans_of(member_id) if include_returned else repo.open_loans_of(member_id)
    return sorted(loans, key=lambda loan: (-loan.borrowed_on.toordinal(), loan.id))
