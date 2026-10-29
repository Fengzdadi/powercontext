"""领域模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class CopyStatus(str, Enum):
    """副本状态。

    实现: DATA-001
    """

    ON_SHELF = "on_shelf"
    ON_LOAN = "on_loan"
    REPAIR = "repair"
    LOST = "lost"


class MemberKind(str, Enum):
    """读者类型，决定借阅上限和借期。

    实现: DATA-003, LOAN-002, LOAN-003
    """

    STUDENT = "student"
    STAFF = "staff"

    @property
    def loan_limit(self) -> int:
        return 5 if self is MemberKind.STUDENT else 10

    @property
    def loan_days(self) -> int:
        return 30 if self is MemberKind.STUDENT else 60


@dataclass
class Book:
    """图书。

    实现: DATA-002
    """

    id: str
    isbn: str
    title: str
    author: str
    category: str
    year: int
    price_cents: int


@dataclass
class Copy:
    """图书的一个实体副本。"""

    id: str
    book_id: str
    barcode: str
    status: CopyStatus


@dataclass
class Member:
    """读者。"""

    id: str
    name: str
    kind: MemberKind
    active: bool


@dataclass
class Loan:
    """一笔借阅。"""

    id: str
    copy_id: str
    member_id: str
    borrowed_on: date
    due_on: date
    returned_on: date | None = None
    renewals: int = 0

    @property
    def is_open(self) -> bool:
        return self.returned_on is None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "copy_id": self.copy_id,
            "member_id": self.member_id,
            "borrowed_on": self.borrowed_on.isoformat(),
            "due_on": self.due_on.isoformat(),
            "returned_on": self.returned_on.isoformat() if self.returned_on else None,
            "renewals": self.renewals,
        }
