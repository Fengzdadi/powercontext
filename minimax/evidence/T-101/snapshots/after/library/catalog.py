"""馆藏检索与详情。"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidParameter, NotFound
from .models import Book, CopyStatus
from .repository import Repository

SORT_KEYS = {
    "id": lambda book: (book.id,),
    "title": lambda book: (book.title, book.id),
    "year": lambda book: (book.year, book.id),
    "-year": lambda book: (-book.year, book.id),
}


@dataclass(frozen=True)
class SearchResult:
    total: int
    page: int
    page_size: int
    items: list[dict]

    def to_dict(self) -> dict:
        return {"total": self.total, "page": self.page, "page_size": self.page_size, "items": self.items}


def available_copies(repo: Repository, book_id: str) -> int:
    """在架副本数，只统计 `on_shelf` 的副本。

    实现: DATA-001
    """
    return sum(1 for copy in repo.copies_of(book_id) if copy.status is CopyStatus.ON_SHELF)


def book_summary(repo: Repository, book: Book) -> dict:
    """检索结果中的一个条目。

    实现: CAT-006
    """
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "category": book.category,
        "year": book.year,
        "copies_available": available_copies(repo, book.id),
    }


def search_books(
    repo: Repository,
    *,
    keyword: str | None = None,
    category: str | None = None,
    available: bool | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    sort: str = "id",
    page: int = 1,
    page_size: int = 10,
) -> SearchResult:
    """按关键词、分类、可借状态和出版年份检索图书，排序后分页。

    实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008
    """
    if year_from is not None and year_to is not None and year_from > year_to:
        raise InvalidParameter("year_from", f"year_from 不能大于 year_to：{year_from} > {year_to}")

    books = list(repo.books.values())

    keyword = (keyword or "").strip().lower()
    if keyword:
        books = [b for b in books if keyword in b.title.lower() or keyword in b.author.lower()]

    if category is not None:
        if category not in repo.categories():
            raise InvalidParameter("category", f"未知的分类：{category}")
        books = [b for b in books if b.category == category]

    if available is not None:
        books = [b for b in books if (available_copies(repo, b.id) > 0) == available]

    if year_from is not None:
        books = [b for b in books if b.year >= year_from]

    if year_to is not None:
        books = [b for b in books if b.year <= year_to]

    if sort not in SORT_KEYS:
        raise InvalidParameter("sort", f"sort 只能是 {', '.join(SORT_KEYS)} 之一")
    books.sort(key=SORT_KEYS[sort])

    total = len(books)
    start = (page - 1) * page_size
    items = [book_summary(repo, book) for book in books[start : start + page_size]]
    return SearchResult(total=total, page=page, page_size=page_size, items=items)


def book_detail(repo: Repository, book_id: str) -> dict:
    """图书详情，包括副本列表和在架副本数。

    实现: CAT-005
    """
    book = repo.books.get(book_id)
    if book is None:
        raise NotFound(f"图书 {book_id} 不存在")
    copies = repo.copies_of(book_id)
    return {
        "id": book.id,
        "isbn": book.isbn,
        "title": book.title,
        "author": book.author,
        "category": book.category,
        "year": book.year,
        "price_cents": book.price_cents,
        "copies_total": len(copies),
        "copies_available": available_copies(repo, book_id),
        "copies": [{"id": c.id, "barcode": c.barcode, "status": c.status.value} for c in copies],
    }
