"""接口处理函数。每个函数返回 `(HTTP 状态码, JSON 对象)`，业务错误直接抛出 LibraryError。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import catalog, loans
from ..catalog import SORT_KEYS
from ..errors import InvalidParameter
from .params import parse_bool, parse_choice, parse_int

if TYPE_CHECKING:
    from .app import AppContext, Request


def list_books(ctx: AppContext, request: Request) -> tuple[int, dict]:
    """GET /books：检索图书。

    实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008, API-005
    """
    params = request.query
    sort = parse_choice(params, "sort", SORT_KEYS, default="id")
    page = parse_int(params, "page", default=1, minimum=1)
    page_size = parse_int(params, "page_size", default=10, minimum=1, maximum=50)
    available = parse_bool(params, "available")
    year_from = parse_int(params, "year_from")
    year_to = parse_int(params, "year_to")
    result = catalog.search_books(
        ctx.repo,
        keyword=params.get("q"),
        category=params.get("category"),
        available=available,
        year_from=year_from,
        year_to=year_to,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return 200, result.to_dict()


def get_book(ctx: AppContext, request: Request, book_id: str) -> tuple[int, dict]:
    """GET /books/{book_id}：图书详情。

    实现: CAT-005
    """
    return 200, catalog.book_detail(ctx.repo, book_id)


def create_loan(ctx: AppContext, request: Request) -> tuple[int, dict]:
    """POST /loans：借书。

    实现: LOAN-001
    """
    body = request.json()
    fields = {}
    for name in ("member_id", "copy_id"):
        value = body.get(name)
        if not isinstance(value, str) or not value.strip():
            raise InvalidParameter(name, f"{name} 必须是非空字符串")
        fields[name] = value.strip()
    loan = loans.borrow(ctx.repo, fields["member_id"], fields["copy_id"], ctx.clock.today())
    return 201, {"loan": loan.to_dict()}


def return_loan(ctx: AppContext, request: Request, loan_id: str) -> tuple[int, dict]:
    """POST /loans/{loan_id}/return：还书并返回罚款。

    实现: LOAN-004, FINE-003
    """
    loan, fine_cents = loans.return_copy(ctx.repo, loan_id, ctx.clock.today())
    return 200, {"loan": loan.to_dict(), "fine_cents": fine_cents}


def renew_loan(ctx: AppContext, request: Request, loan_id: str) -> tuple[int, dict]:
    """POST /loans/{loan_id}/renew：续借。

    实现: LOAN-005
    """
    loan = loans.renew(ctx.repo, loan_id, ctx.clock.today())
    return 200, {"loan": loan.to_dict()}


def member_loans(ctx: AppContext, request: Request, member_id: str) -> tuple[int, dict]:
    """GET /members/{member_id}/loans：读者借阅记录。

    实现: LOAN-006
    """
    include_returned = parse_bool(request.query, "include_returned") or False
    items = loans.member_loans(ctx.repo, member_id, include_returned=include_returned)
    return 200, {"member_id": member_id, "items": [loan.to_dict() for loan in items]}
