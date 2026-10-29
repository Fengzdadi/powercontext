"""馆藏检索服务层测试（search_books）。"""

import pytest

from library.catalog import search_books
from library.errors import InvalidParameter


def book_ids(result) -> list[str]:
    return [item["id"] for item in result.items]


@pytest.mark.spec("CAT-001")
def test_keyword_matches_title_and_author_case_insensitively(repo):
    assert book_ids(search_books(repo, keyword="PYTHON")) == ["B001", "B002"]
    assert book_ids(search_books(repo, keyword="ramalho")) == ["B002"]


@pytest.mark.spec("CAT-001")
def test_blank_keyword_is_ignored(repo):
    assert search_books(repo, keyword="   ").total == search_books(repo).total == 16


@pytest.mark.spec("CAT-002")
def test_category_filter(repo):
    result = search_books(repo, category="hist")
    assert book_ids(result) == ["B011", "B012", "B013"]
    assert {item["category"] for item in result.items} == {"hist"}


@pytest.mark.spec("CAT-002")
def test_unknown_category_is_rejected(repo):
    with pytest.raises(InvalidParameter) as exc:
        search_books(repo, category="music")
    assert exc.value.field == "category"


@pytest.mark.spec("CAT-001", "CAT-002")
def test_keyword_and_category_combine(repo):
    assert len(book_ids(search_books(repo, keyword="a", page_size=50))) == 7
    assert book_ids(search_books(repo, keyword="a", category="math")) == ["B015", "B016"]


@pytest.mark.spec("CAT-003")
def test_default_sort_is_by_id(repo):
    assert book_ids(search_books(repo, page_size=50)) == [f"B{i:03d}" for i in range(1, 17)]


@pytest.mark.spec("CAT-003")
def test_sort_by_year_descending_with_id_tiebreak(repo):
    result = search_books(repo, sort="-year", page_size=50)
    years = [item["year"] for item in result.items]
    assert years == sorted(years, reverse=True)
    # B002 和 B016 同为 2015 年出版，按编号升序
    assert book_ids(result)[2:4] == ["B002", "B016"]


@pytest.mark.spec("CAT-003")
def test_sort_by_title_uses_code_point_order(repo):
    result = search_books(repo, sort="title", page_size=50)
    titles = [item["title"] for item in result.items]
    assert titles == sorted(titles)


@pytest.mark.spec("CAT-004")
def test_pagination_reports_total_before_paging(repo):
    result = search_books(repo, page=2, page_size=10)
    assert result.total == 16
    assert book_ids(result) == [f"B{i:03d}" for i in range(11, 17)]


@pytest.mark.spec("CAT-004")
def test_page_beyond_last_returns_empty_items(repo):
    result = search_books(repo, page=5, page_size=10)
    assert result.total == 16
    assert result.items == []


@pytest.mark.spec("CAT-004", "CAT-002")
def test_total_counts_filtered_books(repo):
    result = search_books(repo, category="cs", page_size=2)
    assert result.total == 5
    assert book_ids(result) == ["B001", "B002"]


@pytest.mark.spec("CAT-006", "DATA-001")
def test_items_include_available_copy_count(repo):
    items = {item["id"]: item for item in search_books(repo, page_size=50).items}
    assert set(items["B001"]) == {"id", "title", "author", "category", "year", "copies_available"}
    assert items["B001"]["copies_available"] == 1  # 一本在架，一本借出
    assert items["B002"]["copies_available"] == 0  # 两本都借出
    assert items["B005"]["copies_available"] == 2
    assert items["B006"]["copies_available"] == 1  # 一本遗失，一本在架
    assert items["B013"]["copies_available"] == 0  # 没有副本
