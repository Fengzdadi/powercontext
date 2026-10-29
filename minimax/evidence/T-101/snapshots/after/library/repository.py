"""内存仓库。启动时从 `data/seed.json` 载入种子数据，每个仓库实例互相独立。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import Book, Copy, CopyStatus, Loan, Member, MemberKind

SEED_PATH = Path(__file__).with_name("data") / "seed.json"


class Repository:
    def __init__(self) -> None:
        self.books: dict[str, Book] = {}
        self.copies: dict[str, Copy] = {}
        self.members: dict[str, Member] = {}
        self.loans: dict[str, Loan] = {}

    @classmethod
    def from_seed(cls, path: Path | None = None) -> "Repository":
        data = json.loads((path or SEED_PATH).read_text(encoding="utf-8"))
        repo = cls()
        for item in data["books"]:
            repo.books[item["id"]] = Book(**item)
        for item in data["copies"]:
            repo.copies[item["id"]] = Copy(**{**item, "status": CopyStatus(item["status"])})
        for item in data["members"]:
            repo.members[item["id"]] = Member(**{**item, "kind": MemberKind(item["kind"])})
        for item in data["loans"]:
            repo.loans[item["id"]] = Loan(
                id=item["id"],
                copy_id=item["copy_id"],
                member_id=item["member_id"],
                borrowed_on=date.fromisoformat(item["borrowed_on"]),
                due_on=date.fromisoformat(item["due_on"]),
                returned_on=date.fromisoformat(item["returned_on"]) if item["returned_on"] else None,
                renewals=item["renewals"],
            )
        return repo

    def categories(self) -> set[str]:
        return {book.category for book in self.books.values()}

    def copies_of(self, book_id: str) -> list[Copy]:
        return sorted((c for c in self.copies.values() if c.book_id == book_id), key=lambda c: c.id)

    def loans_of(self, member_id: str) -> list[Loan]:
        return [loan for loan in self.loans.values() if loan.member_id == member_id]

    def open_loans_of(self, member_id: str) -> list[Loan]:
        return [loan for loan in self.loans_of(member_id) if loan.is_open]

    def next_loan_id(self) -> str:
        numbers = [int(loan_id[1:]) for loan_id in self.loans]
        return f"L{max(numbers, default=0) + 1:03d}"
