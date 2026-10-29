# MiniMax 开发记录：T-101 图书检索增加可借状态和出版年份筛选

| 项目 | 值 |
|---|---|
| 助手 | sddctx MiniMax 开发助手（Anthropic 兼容 Messages API + 工具调用） |
| 模型 / 接口 | `MiniMax-M3.1-Flash` / `https://api.minimax.cn/anthropic/v1/messages` |
| 开始 / 结束 | 2026-10-29T02:23:34.863+00:00 / 2026-10-29T02:25:20.810+00:00 |
| 结果 | finished，13 轮，成功修改 2 次 |
| Token 用量 | 输入 29054（另有缓存命中 256302），输出 5640 |
| 修改的文件 | `library/api/handlers.py`, `library/catalog.py` |
| 最终差异 sha256 | `aab378c430591f02bbbd4763d9e5d73eb6d69678bd6b4cf990ce09c02d8c1b10` |
| 代码版本 | `d8b4de84b1a3` |

## 任务与上下文

任务：读者反馈在图书检索里找不到“现在就能借到的书”，也没办法按出版年份缩小范围。
请为图书检索接口 GET /books 增加两个筛选条件：
1. 可借状态筛选：查询参数 available，为 true 时只返回至少有一本在架副本、现在就能借到的图书，为 false 时只返回暂时借不到的图书；
2. 出版年份区间筛选：查询参数 year_from、year_to，按出版年份筛选，包含两端，可以只给其中一个。
参数值不合法时按统一的错误格式返回 400。新条件可以和现有的关键词、分类条件组合使用。

提供给 MiniMax 的上下文：`runs/T-101/develop/context-20261029-022334.md`（sha256 `e2fa5327af16`），由 seekdb 检索结果和 PowerContext 任务状态生成（PowerContext 记录 `T-101/outcome/002-verify-before`）。首条用户消息（任务说明 + 完整上下文）见文末附录。

## 修改过程

### 第 1 轮

响应 `0731e129ce576bec0422b788a0e67bf4`，模型 `MiniMax-M3.1-Flash`，4.43s，stop_reason `tool_use`，输入 9085 / 输出 64 tokens。

I'll start by exploring the project structure and reading the relevant files.

- 调用 `list_dir`（path="."）
- 调用 `read_file`（path="library/catalog.py"）
  - `list_dir` 结果（成功）：

```
LICENSE
README.md
library/
pyproject.toml
sdd.toml
specs/
tests/
```

  - `read_file` 结果（成功）：

```
library/catalog.py（第 1-107 行，共 107 行）
   1| """馆藏检索与详情。"""
   2| 
   3| from __future__ import annotations
   4| 
   5| from dataclasses import dataclass
   6| 
   7| from .errors import InvalidParameter, NotFound
   8| from .models import Book, CopyStatus
   9| from .repository import Repository
  10| 
  11| SORT_KEYS = {
  12|     "id": lambda book: (book.id,),
  13|     "title": lambda book: (book.title, book.id),
  14|     "year": lambda book: (book.year, book.id),
  15|     "-year": lambda book: (-book.year, book.id),
  16| }
  17| 
  18| 
  19| @dataclass(frozen=True)
  20| class SearchResult:
  21|     total: int
  22|     page: int
  23|     page_size: int
  24|     items: list[dict]
  25| 
  26|     def to_dict(self) -> dict:
  27|         return {"total": self.total, "page": self.page, "page_size": self.page_size, "items": self.items}
  28| 
  29| 
  30| def available_copies(repo: Repository, book_id: str) -> int:
  31|     """在架副本数，只统计 `on_shelf` 的副本。
  32| 
  33|     实现: DATA-001
  34|     """
  35|     return sum(1 for copy in repo.copies_of(book_id) if copy.status is CopyStatus.ON_SHELF)
  36| 
  37| 
  38| def book_summary(repo: Repository, book: Book) -> dict:
  39|…（共 3601 字符）
```

### 第 2 轮

响应 `0731e12c725c8e03b8c772276aaf85ba`，模型 `MiniMax-M3.1-Flash`，3.53s，stop_reason `tool_use`，输入 1379 / 输出 80 tokens。

- 调用 `read_file`（path="library/api/handlers.py"）
- 调用 `read_file`（path="library/api/params.py"）
- 调用 `read_file`（path="library/errors.py"）
  - `read_file` 结果（成功）：

```
library/api/handlers.py（第 1-85 行，共 85 行）
   1| """接口处理函数。每个函数返回 `(HTTP 状态码, JSON 对象)`，业务错误直接抛出 LibraryError。"""
   2| 
   3| from __future__ import annotations
   4| 
   5| from typing import TYPE_CHECKING
   6| 
   7| from .. import catalog, loans
   8| from ..catalog import SORT_KEYS
   9| from ..errors import InvalidParameter
  10| from .params import parse_bool, parse_choice, parse_int
  11| 
  12| if TYPE_CHECKING:
  13|     from .app import AppContext, Request
  14| 
  15| 
  16| def list_books(ctx: AppContext, request: Request) -> tuple[int, dict]:
  17|     """GET /books：检索图书。
  18| 
  19|     实现: CAT-001, CAT-002, CAT-003, CAT-004, API-005
  20|     """
  21|     params = request.query
  22|     sort = parse_choice(params, "sort", SORT_KEYS, default="id")
  23|     page = parse_int(params, "page", default=1, minimum=1)
  24|     page_size = parse_int(params, "page_size", default=10, minimum=1, maximum=50)
  25|     result = catalog.search_books(
  26|         ctx.repo,
  27|         keyword=params.get("q"),
  28|         category=params.get("category"),
  29|         sort=sort,
  30|         page=page,
  31|         page_size=page_size,
  32|     )
  33|     return 200, re…（共 3238 字符）
```

  - `read_file` 结果（成功）：

```
library/api/params.py（第 1-66 行，共 66 行）
   1| """查询参数解析。参数表是 `dict[str, str]`，同名参数只保留第一个值（见 app.parse_query）。"""
   2| 
   3| from __future__ import annotations
   4| 
   5| import re
   6| from collections.abc import Iterable, Mapping
   7| 
   8| from ..errors import InvalidParameter
   9| 
  10| _INT_PATTERN = re.compile(r"[+-]?[0-9]+")
  11| _TRUE_VALUES = {"true", "1"}
  12| _FALSE_VALUES = {"false", "0"}
  13| 
  14| 
  15| def parse_bool(params: Mapping[str, str], name: str) -> bool | None:
  16|     """解析布尔查询参数；参数没有出现时返回 None。
  17| 
  18|     实现: API-003
  19|     """
  20|     if name not in params:
  21|         return None
  22|     value = params[name].strip().lower()
  23|     if value in _TRUE_VALUES:
  24|         return True
  25|     if value in _FALSE_VALUES:
  26|         return False
  27|     raise InvalidParameter(name, f"{name} 只能是 true、false、1 或 0")
  28| 
  29| 
  30| def parse_int(
  31|     params: Mapping[str, str],
  32|     name: str,
  33|     *,
  34|     default: int | None = None,
  35|     minimum: int | None = None,
  36|     maximum: int | None = None,
  37| ) -> int | None:
  38|     """解析整数查询参数并检查范围；参数没有出现时返回 default。
  39| 
  40|     实现: API-…（共 2172 字符）
```

  - `read_file` 结果（成功）：

```
library/errors.py（第 1-48 行，共 48 行）
   1| """业务错误。HTTP 层把它们转换成 API-002 规定的错误响应。"""
   2| 
   3| from __future__ import annotations
   4| 
   5| 
   6| class LibraryError(Exception):
   7|     """所有业务错误的基类。
   8| 
   9|     实现: API-002
  10|     """
  11| 
  12|     status = 500
  13|     code = "internal_error"
  14| 
  15|     def __init__(self, message: str, *, field: str | None = None) -> None:
  16|         super().__init__(message)
  17|         self.message = message
  18|         self.field = field
  19| 
  20|     def to_dict(self) -> dict:
  21|         return {"error": {"code": self.code, "message": self.message, "field": self.field}}
  22| 
  23| 
  24| class InvalidParameter(LibraryError):
  25|     """查询参数或请求体不合法（400）。"""
  26| 
  27|     status = 400
  28|     code = "invalid_parameter"
  29| 
  30|     def __init__(self, field: str, message: str) -> None:
  31|         super().__init__(message, field=field)
  32| 
  33| 
  34| class NotFound(LibraryError):
  35|     """资源不存在（404）。"""
  36| 
  37|     status = 404
  38|     code = "not_found"
  39| 
  40| 
  41| class RuleViolation(LibraryError):
  42|     """违反业务规则（409），错误码由调用方指定。"""
  43| 
  44|     status = 409
  45…（共 1336 字符）
```

### 第 3 轮

响应 `0731e131e2ea5c02b80557cd54e5a4a3`，模型 `MiniMax-M3.1-Flash`，4.23s，stop_reason `tool_use`，输入 2522 / 输出 78 tokens。

> 思考摘要：Now let's look at the tests to understand the expectations, and the app.py for query parsing.

- 调用 `read_file`（path="library/api/app.py"）
- 调用 `read_file`（path="tests/test_api_books_filters.py"）
  - `read_file` 结果（成功）：

```
library/api/app.py（第 1-98 行，共 98 行）
   1| """WSGI 应用：路由、请求解析和错误响应。"""
   2| 
   3| from __future__ import annotations
   4| 
   5| import json
   6| import re
   7| from collections.abc import Callable, Iterable
   8| from dataclasses import dataclass
   9| from http import HTTPStatus
  10| from urllib.parse import parse_qsl
  11| 
  12| from ..clock import Clock, SystemClock
  13| from ..errors import InvalidParameter, LibraryError, NotFound
  14| from ..repository import Repository
  15| from . import handlers
  16| 
  17| ROUTES: list[tuple[str, re.Pattern[str], Callable[..., tuple[int, dict]]]] = [
  18|     ("GET", re.compile(r"/books"), handlers.list_books),
  19|     ("GET", re.compile(r"/books/(?P<book_id>[^/]+)"), handlers.get_book),
  20|     ("POST", re.compile(r"/loans"), handlers.create_loan),
  21|     ("POST", re.compile(r"/loans/(?P<loan_id>[^/]+)/return"), handlers.return_loan),
  22|     ("POST", re.compile(r"/loans/(?P<loan_id>[^/]+)/renew"), handlers.renew_loan),
  23|     ("GET", re.compile(r"/members/(?P<member_id>[^/]+)/loans"), handlers.member_loans),
  24| ]
  25| 
  26| 
  27| @dataclass
  28| class AppContext:
  29|     repo: Repository
  30|     clock: C…（共 3934 字符）
```

  - `read_file` 结果（成功）：

```
tests/test_api_books_filters.py（第 1-128 行，共 128 行）
   1| """GET /books 的可借状态筛选（CAT-007）和出版年份区间筛选（CAT-008）。
   2| 
   3| 这两个条目在 specs/catalog.md 中是“待实现”，本文件是它们的验收测试。
   4| """
   5| 
   6| import pytest
   7| 
   8| from conftest import ids
   9| 
  10| # 种子数据中有在架副本的图书，以及没有在架副本的图书（含没有任何副本的 B013）
  11| AVAILABLE = ["B001", "B003", "B005", "B006", "B008", "B010", "B011", "B014", "B016"]
  12| UNAVAILABLE = ["B002", "B004", "B007", "B009", "B012", "B013", "B015"]
  13| 
  14| 
  15| def assert_invalid(response, field):
  16|     assert response.status == 400
  17|     assert response.json["error"]["code"] == "invalid_parameter"
  18|     assert response.json["error"]["field"] == field
  19| 
  20| 
  21| @pytest.mark.spec("CAT-007", "DATA-001")
  22| def test_available_true_returns_only_books_with_copies_on_shelf(client):
  23|     response = client.get("/books?available=true&page_size=50")
  24|     assert response.status == 200
  25|     assert ids(response) == AVAILABLE
  26|     assert response.json["total"] == len(AVAILABLE)
  27|     assert all(item["copies_available"] > 0 for item in response.json["items"])
  28| 
  29| 
  30| @pytest.mark.spec("CAT-007", "DATA-001")
  31| def t…（共 5712 字符）
```

### 第 4 轮

响应 `0731e1349d981efafbaa13820e449053`，模型 `MiniMax-M3.1-Flash`，5.2s，stop_reason `tool_use`，输入 3330 / 输出 207 tokens。

> 思考摘要：Now let me check the catalog search tests and repository code. Also the `search_books` in library/catalog.py — I need to add `available` and year filters.  Note the `available` filter: `copies_available > 0`. But `book_summary` computes `copies_available` using `available_copies`. However, in `search_books`, the filtering needs `available_copies(repo, book.id)`.  Note also there's an important det…（共 659 字符）

- 调用 `read_file`（path="library/repository.py"）
- 调用 `read_file`（path="tests/test_catalog_search.py"）
  - `read_file` 结果（成功）：

```
library/repository.py（第 1-57 行，共 57 行）
   1| """内存仓库。启动时从 `data/seed.json` 载入种子数据，每个仓库实例互相独立。"""
   2| 
   3| from __future__ import annotations
   4| 
   5| import json
   6| from datetime import date
   7| from pathlib import Path
   8| 
   9| from .models import Book, Copy, CopyStatus, Loan, Member, MemberKind
  10| 
  11| SEED_PATH = Path(__file__).with_name("data") / "seed.json"
  12| 
  13| 
  14| class Repository:
  15|     def __init__(self) -> None:
  16|         self.books: dict[str, Book] = {}
  17|         self.copies: dict[str, Copy] = {}
  18|         self.members: dict[str, Member] = {}
  19|         self.loans: dict[str, Loan] = {}
  20| 
  21|     @classmethod
  22|     def from_seed(cls, path: Path | None = None) -> "Repository":
  23|         data = json.loads((path or SEED_PATH).read_text(encoding="utf-8"))
  24|         repo = cls()
  25|         for item in data["books"]:
  26|             repo.books[item["id"]] = Book(**item)
  27|         for item in data["copies"]:
  28|             repo.copies[item["id"]] = Copy(**{**item, "status": CopyStatus(item["status"])})
  29|         for item in data["members"]:
  30|             repo.members[item["id"]] = Member(*…（共 2592 字符）
```

  - `read_file` 结果（成功）：

```
tests/test_catalog_search.py（第 1-94 行，共 94 行）
   1| """馆藏检索服务层测试（search_books）。"""
   2| 
   3| import pytest
   4| 
   5| from library.catalog import search_books
   6| from library.errors import InvalidParameter
   7| 
   8| 
   9| def book_ids(result) -> list[str]:
  10|     return [item["id"] for item in result.items]
  11| 
  12| 
  13| @pytest.mark.spec("CAT-001")
  14| def test_keyword_matches_title_and_author_case_insensitively(repo):
  15|     assert book_ids(search_books(repo, keyword="PYTHON")) == ["B001", "B002"]
  16|     assert book_ids(search_books(repo, keyword="ramalho")) == ["B002"]
  17| 
  18| 
  19| @pytest.mark.spec("CAT-001")
  20| def test_blank_keyword_is_ignored(repo):
  21|     assert search_books(repo, keyword="   ").total == search_books(repo).total == 16
  22| 
  23| 
  24| @pytest.mark.spec("CAT-002")
  25| def test_category_filter(repo):
  26|     result = search_books(repo, category="hist")
  27|     assert book_ids(result) == ["B011", "B012", "B013"]
  28|     assert {item["category"] for item in result.items} == {"hist"}
  29| 
  30| 
  31| @pytest.mark.spec("CAT-002")
  32| def test_unknown_category_is_rejected(repo):
  33|     with pytest.raises…（共 3891 字符）
```

### 第 5 轮

响应 `0731e13b137b11b0987f833a05c7b3af`，模型 `MiniMax-M3.1-Flash`，8.93s，stop_reason `tool_use`，输入 2406 / 输出 60 tokens。

> 思考摘要：Now let me check the seed data to verify the year ranges and available lists.  Let me check the seed.json for books and copies.

- 调用 `read_file`（path="library/data/seed.json"）
  - `read_file` 结果（成功）：

```
library/data/seed.json（第 1-61 行，共 61 行）
   1| {
   2|   "books": [
   3|     {"id": "B001", "isbn": "9787115428028", "title": "Python 编程：从入门到实践", "author": "Eric Matthes", "category": "cs", "year": 2016, "price_cents": 8900},
   4|     {"id": "B002", "isbn": "9787115454157", "title": "流畅的 Python", "author": "Luciano Ramalho", "category": "cs", "year": 2015, "price_cents": 13900},
   5|     {"id": "B003", "isbn": "9787111544937", "title": "深入理解计算机系统", "author": "Randal E. Bryant", "category": "cs", "year": 2003, "price_cents": 13900},
   6|     {"id": "B004", "isbn": "9787111637301", "title": "数据库系统概念", "author": "Abraham Silberschatz", "category": "cs", "year": 2019, "price_cents": 12900},
   7|     {"id": "B005", "isbn": "9787111407010", "title": "算法导论", "author": "Thomas H. Cormen", "category": "cs", "year": 1990, "price_cents": 12800},
   8|     {"id": "B006", "isbn": "9787020002207", "title": "红楼梦", "author": "曹雪芹", "category": "lit", "year": 1791, "price_cents": 5980},
   9|     {"id": "B007", "isbn": "9787020090006", "title": "围城", "author": "钱锺书", "category": "lit", "year": 1947, "price_cents": 3900},
  10|     {"id": "B008", "isbn": "9787506365437", "title": "活着", "author":…（共 6226 字符）
```

### 第 6 轮

响应 `0731e142aa0f77abbb54b2186862a7a0`，模型 `MiniMax-M3.1-Flash`，17.91s，stop_reason `tool_use`，输入 2680 / 输出 1500 tokens。

> 思考摘要：Now, let me verify the test expectations against seed data.  AVAILABLE (copies_available > 0): B001 (C001 on_shelf), B003 (C005), B005 (C007, C008), B006 (C010), B008 (C012), B010 (C015), B011 (C016), B014 (C018), B016 (C021) → 9 books: B001, B003, B005, B006, B008, B010, B011, B014, B016. Matches AVAILABLE list.  UNAVAILABLE: B002, B004, B007, B009, B012, B013, B015 → matches.  Year tests: - year…（共 4001 字符）

- 调用 `read_file`（path="library/loans.py"）
- 调用 `read_file`（path="tests/conftest.py"）
  - `read_file` 结果（成功）：

```
library/loans.py（第 1-90 行，共 90 行）
   1| """借阅、归还、续借和借阅记录。"""
   2| 
   3| from __future__ import annotations
   4| 
   5| from datetime import date, timedelta
   6| 
   7| from .errors import NotFound, RuleViolation
   8| from .fines import overdue_fine_cents
   9| from .models import CopyStatus, Loan
  10| from .repository import Repository
  11| 
  12| MAX_RENEWALS = 2
  13| 
  14| 
  15| def borrow(repo: Repository, member_id: str, copy_id: str, today: date) -> Loan:
  16|     """借出一个副本。
  17| 
  18|     实现: LOAN-001, LOAN-002, LOAN-003
  19|     """
  20|     member = repo.members.get(member_id)
  21|     if member is None:
  22|         raise NotFound(f"读者 {member_id} 不存在")
  23|     copy = repo.copies.get(copy_id)
  24|     if copy is None:
  25|         raise NotFound(f"副本 {copy_id} 不存在")
  26|     if not member.active:
  27|         raise RuleViolation("member_inactive", f"读者 {member_id} 的账户已停用")
  28|     if copy.status is not CopyStatus.ON_SHELF:
  29|         raise RuleViolation("copy_unavailable", f"副本 {copy_id} 当前不可借（{copy.status.value}）")
  30|     if len(repo.open_loans_of(member_id)) >= member.kind.loan_limit:
  31|         raise RuleViolation("loan_limit_reached", …（共 3529 字符）
```

  - `read_file` 结果（成功）：

```
tests/conftest.py（第 1-72 行，共 72 行）
   1| """测试夹具：每个测试拿到一份新的种子数据和固定日期 2026-10-15。"""
   2| 
   3| from __future__ import annotations
   4| 
   5| import io
   6| import json
   7| from dataclasses import dataclass
   8| from datetime import date
   9| from urllib.parse import urlsplit
  10| 
  11| import pytest
  12| 
  13| from library.api.app import create_app
  14| from library.clock import FixedClock
  15| from library.repository import Repository
  16| 
  17| TODAY = date(2026, 10, 15)
  18| 
  19| 
  20| @dataclass
  21| class Response:
  22|     status: int
  23|     headers: dict[str, str]
  24|     json: dict
  25| 
  26| 
  27| class TestClient:
  28|     """直接调用 WSGI 应用，不经过网络。"""
  29| 
  30|     __test__ = False
  31| 
  32|     def __init__(self, app) -> None:
  33|         self.app = app
  34| 
  35|     def request(self, method: str, url: str, body: dict | None = None) -> Response:
  36|         parts = urlsplit(url)
  37|         raw = json.dumps(body).encode("utf-8") if body is not None else b""
  38|         environ = {
  39|             "REQUEST_METHOD": method,
  40|             "PATH_INFO": parts.path,
  41|             "QUERY_STRING": parts.query,
  42|        …（共 2349 字符）
```

### 第 7 轮

响应 `0731e1566d92d492bb6c786764c4b37b`，模型 `MiniMax-M3.1-Flash`，19.62s，stop_reason `tool_use`，输入 3587 / 输出 2301 tokens。

> 思考摘要：Now let me check the specs/catalog.md to see the exact spec text for CAT-007 and CAT-008 (already in context). And check README for any API docs that should be updated (README might document the endpoint; but README is not in library/ — the instructions say only modify library/ .py files. README is not modifiable? "只修改实现代码（library/ 下的 .py 文件）". So I'll only modify library/.  Let me now implement. …（共 4001 字符）

Now I understand the structure. Let me implement the changes in `library/catalog.py` and `library/api/handlers.py`.

- 调用 `edit_file`：`library/catalog.py`

```diff
--- old_text
+++ new_text
@@ -4,12 +4,18 @@
     keyword: str | None = None,
     category: str | None = None,
+    available: bool | None = None,
+    year_from: int | None = None,
+    year_to: int | None = None,
     sort: str = "id",
     page: int = 1,
     page_size: int = 10,
 ) -> SearchResult:
-    """按关键词和分类检索图书，排序后分页。
+    """按关键词、分类、可借状态和出版年份检索图书，排序后分页。
 
-    实现: CAT-001, CAT-002, CAT-003, CAT-004
+    实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008
     """
+    if year_from is not None and year_to is not None and year_from > year_to:
+        raise InvalidParameter("year_from", f"year_from 不能大于 year_to：{year_from} > {year_to}")
+
     books = list(repo.books.values())
 
@@ -23,3 +29,12 @@
         books = [b for b in books if b.category == category]
 
+    if available is not None:
+        books = [b for b in books if (available_copies(repo, b.id) > 0) == available]
+
+    if year_from is not None:
+        books = [b for b in books if b.year >= year_from]
+
+    if year_to is not None:
+        books = [b for b in books if b.year <= year_to]
+
     if sort not in SORT_KEYS:
```

- 调用 `edit_file`：`library/api/handlers.py`

```diff
--- old_text
+++ new_text
@@ -1,5 +1,5 @@
 """GET /books：检索图书。
 
-    实现: CAT-001, CAT-002, CAT-003, CAT-004, API-005
+    实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008, API-005
     """
     params = request.query
@@ -7,8 +7,14 @@
     page = parse_int(params, "page", default=1, minimum=1)
     page_size = parse_int(params, "page_size", default=10, minimum=1, maximum=50)
+    available = parse_bool(params, "available")
+    year_from = parse_int(params, "year_from")
+    year_to = parse_int(params, "year_to")
     result = catalog.search_books(
         ctx.repo,
         keyword=params.get("q"),
         category=params.get("category"),
+        available=available,
+        year_from=year_from,
+        year_to=year_to,
         sort=sort,
         page=page,
```

  - `edit_file` 结果（成功）：

```
已修改 library/catalog.py（从第 53 行开始，替换 25 行为 40 行）
```

  - `edit_file` 结果（成功）：

```
已修改 library/api/handlers.py（从第 17 行开始，替换 16 行为 22 行）
```

### 第 8 轮

响应 `0731e1686aa1820dd5ba03624a4d3700`，模型 `MiniMax-M3.1-Flash`，4.02s，stop_reason `tool_use`，输入 2368 / 输出 36 tokens。

Now let me run the target tests:

- 调用 `run_tests`（suite="target"）
  - `run_tests` 结果（成功）：

```
target 测试：25 passed, 0 failed，exit 0
```

### 第 9 轮

响应 `0731e1716039365f3678d0d63b5db69a`，模型 `MiniMax-M3.1-Flash`，8.11s，stop_reason `tool_use`，输入 65 / 输出 41 tokens。

All 25 target cases pass. Now the regression suite:

- 调用 `run_tests`（suite="regression"）
  - `run_tests` 结果（成功）：

```
regression 测试：91 passed, 0 failed，exit 0
```

### 第 10 轮

响应 `0731e1773be124e2283016aada3fff24`，模型 `MiniMax-M3.1-Flash`，6.75s，stop_reason `tool_use`，输入 71 / 输出 118 tokens。

> 思考摘要：Both suites pass. Let me double-check the final files to verify correctness and style.

- 调用 `read_file`（end_line=100, path="library/catalog.py", start_line=53）
- 调用 `read_file`（end_line=42, path="library/api/handlers.py", start_line=16）
  - `read_file` 结果（成功）：

```
library/catalog.py（第 53-100 行，共 122 行）
  53| def search_books(
  54|     repo: Repository,
  55|     *,
  56|     keyword: str | None = None,
  57|     category: str | None = None,
  58|     available: bool | None = None,
  59|     year_from: int | None = None,
  60|     year_to: int | None = None,
  61|     sort: str = "id",
  62|     page: int = 1,
  63|     page_size: int = 10,
  64| ) -> SearchResult:
  65|     """按关键词、分类、可借状态和出版年份检索图书，排序后分页。
  66| 
  67|     实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008
  68|     """
  69|     if year_from is not None and year_to is not None and year_from > year_to:
  70|         raise InvalidParameter("year_from", f"year_from 不能大于 year_to：{year_from} > {year_to}")
  71| 
  72|     books = list(repo.books.values())
  73| 
  74|     keyword = (keyword or "").strip().lower()
  75|     if keyword:
  76|         books = [b for b in books if keyword in b.title.lower() or keyword in b.author.lower()]
  77| 
  78|     if category is not None:
  79|         if category not in repo.categories():
  80|             raise InvalidParameter("category", f"未知的分类：{category}")
  81|         books = [b for b in books if b.category == category]
  82| 
…（共 1991 字符）
```

  - `read_file` 结果（成功）：

```
library/api/handlers.py（第 16-42 行，共 91 行）
  16| def list_books(ctx: AppContext, request: Request) -> tuple[int, dict]:
  17|     """GET /books：检索图书。
  18| 
  19|     实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008, API-005
  20|     """
  21|     params = request.query
  22|     sort = parse_choice(params, "sort", SORT_KEYS, default="id")
  23|     page = parse_int(params, "page", default=1, minimum=1)
  24|     page_size = parse_int(params, "page_size", default=10, minimum=1, maximum=50)
  25|     available = parse_bool(params, "available")
  26|     year_from = parse_int(params, "year_from")
  27|     year_to = parse_int(params, "year_to")
  28|     result = catalog.search_books(
  29|         ctx.repo,
  30|         keyword=params.get("q"),
  31|         category=params.get("category"),
  32|         available=available,
  33|         year_from=year_from,
  34|         year_to=year_to,
  35|         sort=sort,
  36|         page=page,
  37|         page_size=page_size,
  38|     )
  39|     return 200, result.to_dict()
  40| 
  41| 
  42| def get_book(ctx: AppContext, request: Request, book_id: str) -> tuple[int, dict]:
…（共 91 行，只显示到第 42 行）
```

### 第 11 轮

响应 `0731e17b6e7970466f612cda6ba0fd77`，模型 `MiniMax-M3.1-Flash`，5.44s，stop_reason `tool_use`，输入 1236 / 输出 250 tokens。

> 思考摘要：Everything looks good. Let me also verify behavior consistency: with no new params, results are unchanged (available=None, year_from=None, year_to=None → no filtering). ✓  Also let me sanity-check a few edge cases manually, e.g. `available=1` handled by parse_bool; `year_from=+3` handled by parse_int. And the `available=false` case for a book with a `repair` copy only (B004) → copies_available 0 →…（共 810 字符）

Let me do a quick manual sanity check of edge cases:

- 调用 `search`（path="README.md", pattern="available|year_from|year_to"）
  - `search` 结果（成功）：

```
没有匹配
```

### 第 12 轮

响应 `0731e182d670076f4af192c1560b2c0a`，模型 `MiniMax-M3.1-Flash`，5.54s，stop_reason `tool_use`，输入 268 / 输出 28 tokens。

- 调用 `run_tests`（suite="all"）
  - `run_tests` 结果（成功）：

```
all 测试：116 passed, 0 failed，exit 0
```

### 第 13 轮

响应 `0731e1887230a7ef555eee3ed4fb4a09`，模型 `MiniMax-M3.1-Flash`，11.34s，stop_reason `tool_use`，输入 57 / 输出 877 tokens。

> 思考摘要：All 116 tests pass (25 target + 91 regression).  Let me double check the README to see if it documents the endpoint - grep found no matches for available/year_from, so no docs update needed there (and README isn't a library/ .py file anyway).  Everything's complete. Let me call finish.

全部测试通过（116 = 25 目标 + 91 回归）。改动总结：

**`library/catalog.py::search_books`**
- 新增关键字参数 `available: bool | None`、`year_from: int | None`、`year_to: int | None`。
- `available` 过滤复用已有的 `available_copies()`（DATA-001，只统计 `on_shelf` 副本）：`available=True` 保留 `copies_available > 0` 的书，`available=False` 保留在架副本数为 0 的书（含无任何副本的书）；`None`（参数缺省）不筛选。
- 年份按闭区间过滤：`year_from` 存在时保留 `book.year >= year_from`，`year_to` 存在时保留 `book.year <= year_to`，可只给其一。
- `year_from > year_to` 时抛 `InvalidParameter("year_from", ...)`（400 / `invalid_parameter` / field=`year_from`），校验放在筛选前。
- 所有筛选均在 `sort` 与分页之前执行，`total` 为筛选后的总数；docstring 标注 `实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008`。

**`library/api/handlers.py::list_books`**
- 复用现有参数解析函数：`parse_bool(params, "available")`（API-003，非法值自动 400，field=`available`）、`parse_int(params, "year_from")` / `parse_int(params, "year_to")`（API-004，非整数自动 400，field 为对应参数名），并透传给 `catalog.search_books`。
- docstring 标注 `实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008, API-005`。

原有 `q`、`category`、`sort`、`page/page_size` 的行为、错误提示以及其他接口（详情、借阅、归还、续借、罚款）均未改动；不带新参数时结果、排序、分页与改前完全一致。

**测试结果**：目标测试 25 passed / 0 failed；回归测试 91 passed / 0 failed（全量 116 passed）。

- 调用 `finish`：实现 T-101：GET /books 增加可借状态与出版年份筛选。

改动文件：
1. library/catalog.py::search_books —— 新增 available / year_from / year_to 三个关键字参数：
   - available 复用已有 available_copies()（DATA-001，只计 on_shelf 副本）做过滤，True 取 copies_available>0，False 取 copies_available=0（含无副本图书），缺省不筛选；
   - 年份按闭区间过滤，两个参数可只给其一；
   - year_from > year_to 抛 InvalidParameter("year_from")，即 400/invalid_parameter/field=year_from；
   - 所有筛选在 sort 与分页之前执行，total 为筛选后总数；docstring 标注 实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008。
2. library/api/handlers.py::list_books —— 复用现有 parse_bool/parse_int 解析 available、year_from、year_to（非法值统一按 API-002 返回 400，field 为对应参数名），并透传给 search_books；docstring 补 CAT-007、CAT-008 标注。

保持原有行为：q/category/sort/page/page_size 的行为与错误提示不变，不带新参数时结果、排序、分页与改前一致，其他接口未改动。

测试结果：目标测试 25 passed / 0 failed；回归测试 91 passed / 0 failed（全量 116 passed）。

## 最终结果

MiniMax 的完成说明：实现 T-101：GET /books 增加可借状态与出版年份筛选。

改动文件：
1. library/catalog.py::search_books —— 新增 available / year_from / year_to 三个关键字参数：
   - available 复用已有 available_copies()（DATA-001，只计 on_shelf 副本）做过滤，True 取 copies_available>0，False 取 copies_available=0（含无副本图书），缺省不筛选；
   - 年份按闭区间过滤，两个参数可只给其一；
   - year_from > year_to 抛 InvalidParameter("year_from")，即 400/invalid_parameter/field=year_from；
   - 所有筛选在 sort 与分页之前执行，total 为筛选后总数；docstring 标注 实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008。
2. library/api/handlers.py::list_books —— 复用现有 parse_bool/parse_int 解析 available、year_from、year_to（非法值统一按 API-002 返回 400，field 为对应参数名），并透传给 search_books；docstring 补 CAT-007、CAT-008 标注。

保持原有行为：q/category/sort/page/page_size 的行为与错误提示不变，不带新参数时结果、排序、分页与改前一致，其他接口未改动。

测试结果：目标测试 25 passed / 0 failed；回归测试 91 passed / 0 failed（全量 116 passed）。

助手最后一次自测：target 25 passed / 0 failed；regression 91 passed / 0 failed；all 116 passed / 0 failed

最终代码差异（相对修改前的工程）：

```diff
diff --git a/library/api/handlers.py b/library/api/handlers.py
--- a/library/api/handlers.py
+++ b/library/api/handlers.py
@@ -16,16 +16,22 @@
 def list_books(ctx: AppContext, request: Request) -> tuple[int, dict]:
     """GET /books：检索图书。
 
-    实现: CAT-001, CAT-002, CAT-003, CAT-004, API-005
+    实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008, API-005
     """
     params = request.query
     sort = parse_choice(params, "sort", SORT_KEYS, default="id")
     page = parse_int(params, "page", default=1, minimum=1)
     page_size = parse_int(params, "page_size", default=10, minimum=1, maximum=50)
+    available = parse_bool(params, "available")
+    year_from = parse_int(params, "year_from")
+    year_to = parse_int(params, "year_to")
     result = catalog.search_books(
         ctx.repo,
         keyword=params.get("q"),
         category=params.get("category"),
+        available=available,
+        year_from=year_from,
+        year_to=year_to,
         sort=sort,
         page=page,
         page_size=page_size,
diff --git a/library/catalog.py b/library/catalog.py
--- a/library/catalog.py
+++ b/library/catalog.py
@@ -55,14 +55,20 @@
     *,
     keyword: str | None = None,
     category: str | None = None,
+    available: bool | None = None,
+    year_from: int | None = None,
+    year_to: int | None = None,
     sort: str = "id",
     page: int = 1,
     page_size: int = 10,
 ) -> SearchResult:
-    """按关键词和分类检索图书，排序后分页。
+    """按关键词、分类、可借状态和出版年份检索图书，排序后分页。
 
-    实现: CAT-001, CAT-002, CAT-003, CAT-004
+    实现: CAT-001, CAT-002, CAT-003, CAT-004, CAT-007, CAT-008
     """
+    if year_from is not None and year_to is not None and year_from > year_to:
+        raise InvalidParameter("year_from", f"year_from 不能大于 year_to：{year_from} > {year_to}")
+
     books = list(repo.books.values())
 
     keyword = (keyword or "").strip().lower()
@@ -73,6 +79,15 @@
         if category not in repo.categories():
             raise InvalidParameter("category", f"未知的分类：{category}")
         books = [b for b in books if b.category == category]
+
+    if available is not None:
+        books = [b for b in books if (available_copies(repo, b.id) > 0) == available]
+
+    if year_from is not None:
+        books = [b for b in books if b.year >= year_from]
+
+    if year_to is not None:
+        books = [b for b in books if b.year <= year_to]
 
     if sort not in SORT_KEYS:
         raise InvalidParameter("sort", f"sort 只能是 {', '.join(SORT_KEYS)} 之一")

```

## 附录：发给 MiniMax 的首条消息

<details><summary>展开（任务说明 + 上下文模块输出）</summary>

````markdown
# 开发任务 T-101：图书检索增加可借状态和出版年份筛选

读者反馈在图书检索里找不到“现在就能借到的书”，也没办法按出版年份缩小范围。
请为图书检索接口 GET /books 增加两个筛选条件：
1. 可借状态筛选：查询参数 available，为 true 时只返回至少有一本在架副本、现在就能借到的图书，为 false 时只返回暂时借不到的图书；
2. 出版年份区间筛选：查询参数 year_from、year_to，按出版年份筛选，包含两端，可以只给其中一个。
参数值不合法时按统一的错误格式返回 400。新条件可以和现有的关键词、分类条件组合使用。

必须保持的原有行为：
- 不带新参数时，GET /books 的结果、排序和分页与修改前完全一致
- 关键词 q、分类 category、排序 sort、分页 page/page_size 的现有行为和错误提示保持不变
- 所有筛选条件在排序和分页之前生效，total 是筛选后的总数
- 图书详情、借阅、归还、续借、罚款等其他接口的行为不变

工具里的路径都相对工程根目录（例如 library/catalog.py）。目标测试：
- tests/test_api_books_filters.py::test_available_true_returns_only_books_with_copies_on_shelf
- tests/test_api_books_filters.py::test_available_false_returns_only_books_without_copies_on_shelf
- tests/test_api_books_filters.py::test_available_accepts_true_spellings
- tests/test_api_books_filters.py::test_available_accepts_false_spellings
- tests/test_api_books_filters.py::test_invalid_available_value_is_rejected
- tests/test_api_books_filters.py::test_year_range_is_inclusive
- tests/test_api_books_filters.py::test_single_year_range
- tests/test_api_books_filters.py::test_year_from_alone
- tests/test_api_books_filters.py::test_year_to_alone
- tests/test_api_books_filters.py::test_non_integer_year_is_rejected
- tests/test_api_books_filters.py::test_year_from_after_year_to_is_rejected
- tests/test_api_books_filters.py::test_filters_combine_with_keyword_and_category
- tests/test_api_books_filters.py::test_filters_apply_before_pagination
- tests/test_api_books_filters.py::test_filters_apply_before_sorting
- tests/test_api_books_filters.py::test_available_filter_follows_loans_and_returns

下面是上下文模块为本任务生成的上下文。

---

# 任务上下文：T-101 图书检索增加可借状态和出版年份筛选

> 工程 `campus-library`；资料来自 seekdb 导入批次 #1（161 个片段，工程目录指纹 `8acd5172039b`，代码版本 `d8b4de84b1a3`）。引用的来源 81 处，逐行核对一致 81 处。

## 0. 任务

读者反馈在图书检索里找不到“现在就能借到的书”，也没办法按出版年份缩小范围。
请为图书检索接口 GET /books 增加两个筛选条件：
1. 可借状态筛选：查询参数 available，为 true 时只返回至少有一本在架副本、现在就能借到的图书，为 false 时只返回暂时借不到的图书；
2. 出版年份区间筛选：查询参数 year_from、year_to，按出版年份筛选，包含两端，可以只给其中一个。
参数值不合法时按统一的错误格式返回 400。新条件可以和现有的关键词、分类条件组合使用。

必须保持的原有行为：

- 不带新参数时，GET /books 的结果、排序和分页与修改前完全一致
- 关键词 q、分类 category、排序 sort、分页 page/page_size 的现有行为和错误提示保持不变
- 所有筛选条件在排序和分页之前生效，total 是筛选后的总数
- 图书详情、借阅、归还、续借、罚款等其他接口的行为不变

## 1. 适用规格

### 1.1 本次要实现的条目

#### CAT-007 可借状态筛选（待实现）

来源 `specs/catalog.md:61-78`，修订 r1，内容 sha256 `d2fefa4d8922`。选择依据：任务检索命中：第 2 名（全文第 3 名，向量第 2 名，RRF 0.0320）。

```markdown
### CAT-007 可借状态筛选
- 状态：待实现
- 接口：GET /books?available=
- 关联：API-002, API-003, DATA-001, CAT-004

新增布尔参数 `available`，按 API-003 解析：

- `available=true`：只返回至少有一个在架副本（DATA-001 中的 `on_shelf`）的图书，即 `copies_available > 0`；
- `available=false`：只返回没有在架副本的图书（包括没有任何副本的图书）；
- 不提供该参数：不按可借状态筛选，结果与现在一致。

`available` 可以和 `q`、`category`、`year_from`、`year_to` 同时使用，条件之间是“且”的关系；筛选在排序和分页之前生效，`total` 是筛选后的总数（CAT-004）。参数值不合法时返回 400，错误码 `invalid_parameter`，`field` 为 `available`（API-002）。

验收：
- `available=true` 只返回 `copies_available > 0` 的图书。
- `available=false` 只返回 `copies_available` 为 0 的图书。
- `available=TRUE`、`available=1` 与 `available=true` 等价。
- `available=yes` 返回 400 `invalid_parameter`，`field` 为 `available`。
```

#### CAT-008 出版年份区间筛选（待实现）

来源 `specs/catalog.md:80-90`，修订 r1，内容 sha256 `ebfa50ed0e07`。选择依据：任务检索命中：第 1 名（全文第 2 名，向量第 1 名，RRF 0.0325）。

```markdown
### CAT-008 出版年份区间筛选
- 状态：待实现
- 接口：GET /books?year_from=&year_to=
- 关联：API-002, API-004, CAT-004

新增整数参数 `year_from`、`year_to`（按 API-004 解析），表示出版年份的闭区间 `[year_from, year_to]`，两个参数可以只提供一个。参数不是整数时返回 400 `invalid_parameter`，`field` 为对应参数名；同时提供且 `year_from` 大于 `year_to` 时返回 400 `invalid_parameter`，`field` 为 `year_from`。年份筛选同样可以和其他条件组合，并在分页之前生效（CAT-004）。

验收：
- `year_from=2000&year_to=2015` 包含 2000 年和 2015 年出版的图书。
- 只给 `year_to=1950` 时返回 1950 年及以前出版的图书。
- `year_from=2020&year_to=2010` 返回 400 `invalid_parameter`，`field` 为 `year_from`。
```

### 1.2 必须遵守的约束（被目标条目引用或被任务检索命中）

#### API-002 错误格式（已实现）

来源 `specs/api.md:15-26`，修订 r1，内容 sha256 `d4b49d7b2746`。选择依据：被 CAT-007 引用；被 CAT-008 引用。

```markdown
### API-002 错误格式
- 状态：已实现
- 关联：API-001

错误响应体为 `{"error": {"code": 错误码, "message": 说明, "field": 出错的参数名或 null}}`。

- 查询参数或请求体不合法：400，错误码 `invalid_parameter`，`field` 为参数名；
- 资源不存在：404，错误码 `not_found`，`field` 为 null；
- 违反业务规则：409，使用具体的错误码（例如 `loan_limit_reached`），`field` 为 null。

验收：
- `GET /books?page=0` 返回 400，响应体 `error.code` 为 `invalid_parameter`，`error.field` 为 `page`。
```

#### API-003 布尔查询参数（已实现）

来源 `specs/api.md:30-38`，修订 r1，内容 sha256 `6a8bdde45e7a`。选择依据：被 CAT-007 引用。

```markdown
### API-003 布尔查询参数
- 状态：已实现
- 关联：API-002

布尔查询参数接受 `true`、`false`、`1`、`0`，不区分大小写，忽略前后空白；`true`、`1` 为真，`false`、`0` 为假。参数出现但取值不在上述范围（包括空字符串）时返回 400 `invalid_parameter`，`field` 为参数名。参数没有出现时由各接口决定默认行为。

验收：
- `include_returned=True` 与 `include_returned=1` 等价。
- `include_returned=yes` 返回 400 `invalid_parameter`，`field` 为 `include_returned`。
```

#### API-004 整数查询参数（已实现）

来源 `specs/api.md:40-47`，修订 r1，内容 sha256 `70a4acc9a6d1`。选择依据：被 CAT-008 引用。

```markdown
### API-004 整数查询参数
- 状态：已实现
- 关联：API-002

整数查询参数只接受十进制 ASCII 数字，可以带一个正负号，忽略前后空白（例如 `" 7 "`、`"+3"`、`"-2"`）。不是整数时（例如 `"abc"`、`"1.5"`、`"1_000"`、空字符串）返回 400 `invalid_parameter`，`field` 为参数名。取值范围由各接口规定，超出范围同样返回 400 `invalid_parameter`。

验收：
- `page=abc` 返回 400 `invalid_parameter`，`field` 为 `page`。
```

#### CAT-002 分类筛选（已实现）

来源 `specs/catalog.md:18-27`，修订 r1，内容 sha256 `bc4e1756b76d`。选择依据：任务检索命中：第 3 名（全文第 6 名，向量第 7 名，RRF 0.0301）。

```markdown
### CAT-002 分类筛选
- 状态：已实现
- 接口：GET /books?category=
- 关联：API-002

参数 `category` 按分类代码精确匹配，馆藏分类代码为 `cs`（计算机）、`lit`（文学）、`hist`（历史）、`math`（数学）。馆藏中不存在的分类返回 400，错误码 `invalid_parameter`，`field` 为 `category`。

验收：
- `category=hist` 只返回历史类图书。
- `category=music` 返回 400 `invalid_parameter`，`field` 为 `category`。
```

#### CAT-003 排序（已实现）

来源 `specs/catalog.md:29-38`，修订 r1，内容 sha256 `f9a6be074caa`。选择依据：任务检索命中：第 4 名（全文第 15 名，向量第 3 名，RRF 0.0292）。

```markdown
### CAT-003 排序
- 状态：已实现
- 接口：GET /books?sort=
- 关联：API-002

参数 `sort` 取值：`id`（默认，按图书编号升序）、`title`（按书名的 Unicode 码位升序）、`year`（按出版年份升序）、`-year`（按出版年份降序）。排序键相同的图书按图书编号升序，保证结果稳定。其他取值返回 400 `invalid_parameter`，`field` 为 `sort`。

验收：
- `sort=-year` 时出版年份大的在前，同年份按编号升序。
- `sort=price` 返回 400 `invalid_parameter`。
```

#### CAT-004 分页（已实现）

来源 `specs/catalog.md:40-49`，修订 r1，内容 sha256 `dfd175ed5d97`。选择依据：被 CAT-007 引用；被 CAT-008 引用。

```markdown
### CAT-004 分页
- 状态：已实现
- 接口：GET /books?page=&page_size=
- 关联：API-004

`page` 默认 1，`page_size` 默认 10、最大 50，二者都必须是正整数，否则返回 400 `invalid_parameter`，`field` 为对应参数名。响应为 `{"total": 符合条件的图书总数, "page": 当前页, "page_size": 每页条数, "items": [...]}`。所有筛选条件都在排序和分页之前生效，`total` 是筛选后的总数。页码超出末页时返回空的 `items`，`total` 不变。

验收：
- 共 16 本书时，`page=2&page_size=10` 返回 6 条，`total` 为 16。
- `page_size=51` 返回 400 `invalid_parameter`，`field` 为 `page_size`。
```

#### DATA-001 副本状态（已实现）

来源 `specs/data.md:5-19`，修订 r1，内容 sha256 `6f3f4ab02184`。选择依据：被 CAT-007 引用。

```markdown
### DATA-001 副本状态
- 状态：已实现
- 关联：CAT-005, CAT-006

每本图书可以有零个或多个副本，副本的 `status` 取值：

- `on_shelf`：在架，可以借阅；
- `on_loan`：已借出；
- `repair`：修补中，不可借；
- `lost`：遗失，不可借。

只有 `on_shelf` 的副本计入“在架副本数”（`copies_available`）。借出时副本变为 `on_loan`，归还后恢复为 `on_shelf`。

验收：
- 一本书有一个 `lost` 副本和一个 `on_shelf` 副本时，在架副本数为 1。
```

### 1.3 同一接口的已实现条目（行为必须保持，属于回归范围）

- **CAT-001 关键词检索**（已实现）— `specs/catalog.md:7-16`，修订 r1。与目标同属分组「图书检索 `GET /books`」
- **CAT-006 检索结果条目**（已实现）— `specs/catalog.md:51-59`，修订 r1。与目标同属分组「图书检索 `GET /books`」

## 2. 代码

### 2.1 需要修改的符号

#### `library/api/handlers.py::list_books`（第 16-33 行）

选择依据：实现同一接口的 4 个已有条目；实现 CAT-001, CAT-002, CAT-003, CAT-004；代码检索第 5 名。

```python
def list_books(ctx: AppContext, request: Request) -> tuple[int, dict]:
    """GET /books：检索图书。

    实现: CAT-001, CAT-002, CAT-003, CAT-004, API-005
    """
    params = request.query
    sort = parse_choice(params, "sort", SORT_KEYS, default="id")
    page = parse_int(params, "page", default=1, minimum=1)
    page_size = parse_int(params, "page_size", default=10, minimum=1, maximum=50)
    result = catalog.search_books(
        ctx.repo,
        keyword=params.get("q"),
        category=params.get("category"),
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return 200, result.to_dict()
```

#### `library/catalog.py::search_books`（第 53-84 行）

选择依据：实现同一接口的 4 个已有条目；实现 CAT-001, CAT-002, CAT-003, CAT-004。

```python
def search_books(
    repo: Repository,
    *,
    keyword: str | None = None,
    category: str | None = None,
    sort: str = "id",
    page: int = 1,
    page_size: int = 10,
) -> SearchResult:
    """按关键词和分类检索图书，排序后分页。

    实现: CAT-001, CAT-002, CAT-003, CAT-004
    """
    books = list(repo.books.values())

    keyword = (keyword or "").strip().lower()
    if keyword:
        books = [b for b in books if keyword in b.title.lower() or keyword in b.author.lower()]

    if category is not None:
        if category not in repo.categories():
            raise InvalidParameter("category", f"未知的分类：{category}")
        books = [b for b in books if b.category == category]

    if sort not in SORT_KEYS:
        raise InvalidParameter("sort", f"sort 只能是 {', '.join(SORT_KEYS)} 之一")
    books.sort(key=SORT_KEYS[sort])

    total = len(books)
    start = (page - 1) * page_size
    items = [book_summary(repo, book) for book in books[start : start + page_size]]
    return SearchResult(total=total, page=page, page_size=page_size, items=items)
```

### 2.2 相关代码（可复用，通常不需要修改）

- `library/catalog.py::available_copies`（第 30-35 行）`def available_copies(repo: Repository, book_id: str) -> int` — 实现 DATA-001；代码检索第 2 名
- `library/api/params.py::parse_bool`（第 15-27 行）`def parse_bool(params: Mapping[str, str], name: str) -> bool | None` — 实现 API-003；代码检索第 4 名
- `library/api/app.py::LibraryApp`（第 61-94 行）`class LibraryApp` — 实现 API-002；代码检索第 9 名
- `library/catalog.py::book_summary`（第 38-50 行）`def book_summary(repo: Repository, book: Book) -> dict` — 实现 CAT-006
- `library/api/params.py::parse_choice`（第 55-66 行）`def parse_choice(params: Mapping[str, str], name: str, choices: Iterable[str], default: str) -> str` — 实现 API-002
- `library/api/params.py::parse_int`（第 30-52 行）`def parse_int( params: Mapping[str, str], name: str, *, default: int | None = None, minimum: int | None = None, maximum: int | None = None, ) -> int | None` — 实现 API-004
- `library/errors.py::LibraryError`（第 6-21 行）`class LibraryError(Exception)` — 实现 API-002
- `library/models.py::CopyStatus`（第 10-19 行）`class CopyStatus(str, Enum)` — 实现 DATA-001
- `library/api/params.py::library.api.params`（第 1-12 行）`module library.api.params` — 代码检索第 1 名
- `library/fines.py::overdue_fine_cents`（第 10-18 行）`def overdue_fine_cents(due_on: date, returned_on: date, price_cents: int) -> int` — 代码检索第 3 名
- `library/loans.py::borrow`（第 15-42 行）`def borrow(repo: Repository, member_id: str, copy_id: str, today: date) -> Loan` — 代码检索第 6 名
- `library/__init__.py::library`（第 1-3 行）`module library` — 代码检索第 7 名

## 3. 测试

### 3.1 目标测试（验证 CAT-007, CAT-008；修改前应因功能未实现而失败，修改后必须全部通过）

- `tests/test_api_books_filters.py::test_available_true_returns_only_books_with_copies_on_shelf`（第 21-27 行）验证 CAT-007, DATA-001
- `tests/test_api_books_filters.py::test_available_false_returns_only_books_without_copies_on_shelf`（第 30-36 行）验证 CAT-007, DATA-001
- `tests/test_api_books_filters.py::test_available_accepts_true_spellings`（第 39-42 行）验证 API-003, CAT-007
- `tests/test_api_books_filters.py::test_available_accepts_false_spellings`（第 45-48 行）验证 API-003, CAT-007
- `tests/test_api_books_filters.py::test_invalid_available_value_is_rejected`（第 51-54 行）验证 API-002, API-003, CAT-007
- `tests/test_api_books_filters.py::test_year_range_is_inclusive`（第 57-61 行）验证 CAT-008
- `tests/test_api_books_filters.py::test_single_year_range`（第 64-66 行）验证 CAT-008
- `tests/test_api_books_filters.py::test_year_from_alone`（第 69-71 行）验证 CAT-008
- `tests/test_api_books_filters.py::test_year_to_alone`（第 74-76 行）验证 CAT-008
- `tests/test_api_books_filters.py::test_non_integer_year_is_rejected`（第 79-90 行）验证 API-002, API-004, CAT-008
- `tests/test_api_books_filters.py::test_year_from_after_year_to_is_rejected`（第 93-95 行）验证 API-002, CAT-008
- `tests/test_api_books_filters.py::test_filters_combine_with_keyword_and_category`（第 98-103 行）验证 CAT-001, CAT-002, CAT-007, CAT-008
- `tests/test_api_books_filters.py::test_filters_apply_before_pagination`（第 106-113 行）验证 CAT-004, CAT-007
- `tests/test_api_books_filters.py::test_filters_apply_before_sorting`（第 116-119 行）验证 CAT-003, CAT-007
- `tests/test_api_books_filters.py::test_available_filter_follows_loans_and_returns`（第 122-128 行）验证 CAT-007, DATA-001

运行：`python -m pytest -q tests/test_api_books_filters.py::test_available_true_returns_only_books_with_copies_on_shelf tests/test_api_books_filters.py::test_available_false_returns_only_books_without_copies_on_shelf tests/test_api_books_filters.py::test_available_accepts_true_spellings tests/test_api_books_filters.py::test_available_accepts_false_spellings tests/test_api_books_filters.py::test_invalid_available_value_is_rejected tests/test_api_books_filters.py::test_year_range_is_inclusive tests/test_api_books_filters.py::test_single_year_range tests/test_api_books_filters.py::test_year_from_alone tests/test_api_books_filters.py::test_year_to_alone tests/test_api_books_filters.py::test_non_integer_year_is_rejected tests/test_api_books_filters.py::test_year_from_after_year_to_is_rejected tests/test_api_books_filters.py::test_filters_combine_with_keyword_and_category tests/test_api_books_filters.py::test_filters_apply_before_pagination tests/test_api_books_filters.py::test_filters_apply_before_sorting tests/test_api_books_filters.py::test_available_filter_follows_loans_and_returns`

```python
@pytest.mark.spec("CAT-007", "DATA-001")
def test_available_true_returns_only_books_with_copies_on_shelf(client):
    response = client.get("/books?available=true&page_size=50")
    assert response.status == 200
    assert ids(response) == AVAILABLE
    assert response.json["total"] == len(AVAILABLE)
    assert all(item["copies_available"] > 0 for item in response.json["items"])
```

```python
@pytest.mark.spec("CAT-007", "DATA-001")
def test_available_false_returns_only_books_without_copies_on_shelf(client):
    response = client.get("/books?available=false&page_size=50")
    assert response.status == 200
    assert ids(response) == UNAVAILABLE
    assert response.json["total"] == len(UNAVAILABLE)
    assert all(item["copies_available"] == 0 for item in response.json["items"])
```

```python
@pytest.mark.spec("CAT-007", "API-003")
@pytest.mark.parametrize("raw", ["TRUE", "True", "1", "%20true%20"])
def test_available_accepts_true_spellings(client, raw):
    assert ids(client.get(f"/books?available={raw}&page_size=50")) == AVAILABLE
```

```python
@pytest.mark.spec("CAT-007", "API-003")
@pytest.mark.parametrize("raw", ["FALSE", "0"])
def test_available_accepts_false_spellings(client, raw):
    assert ids(client.get(f"/books?available={raw}&page_size=50")) == UNAVAILABLE
```

```python
@pytest.mark.spec("CAT-007", "API-002", "API-003")
@pytest.mark.parametrize("raw", ["yes", "", "2", "on"])
def test_invalid_available_value_is_rejected(client, raw):
    assert_invalid(client.get(f"/books?available={raw}"), "available")
```

```python
@pytest.mark.spec("CAT-008")
def test_year_range_is_inclusive(client):
    response = client.get("/books?year_from=2000&year_to=2015&page_size=50")
    assert response.status == 200
    assert ids(response) == ["B002", "B003", "B009", "B012", "B014", "B016"]
```

```python
@pytest.mark.spec("CAT-008")
def test_single_year_range(client):
    assert ids(client.get("/books?year_from=2015&year_to=2015")) == ["B002", "B016"]
```

```python
@pytest.mark.spec("CAT-008")
def test_year_from_alone(client):
    assert ids(client.get("/books?year_from=2016")) == ["B001", "B004"]
```

```python
@pytest.mark.spec("CAT-008")
def test_year_to_alone(client):
    assert ids(client.get("/books?year_to=1950")) == ["B006", "B007"]
```

```python
@pytest.mark.spec("CAT-008", "API-002", "API-004")
@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("year_from=abc", "year_from"),
        ("year_from=2000.5", "year_from"),
        ("year_to=20x5", "year_to"),
        ("year_to=", "year_to"),
    ],
)
def test_non_integer_year_is_rejected(client, query, field):
    assert_invalid(client.get(f"/books?{query}"), field)
```

```python
@pytest.mark.spec("CAT-008", "API-002")
def test_year_from_after_year_to_is_rejected(client):
    assert_invalid(client.get("/books?year_from=2020&year_to=2010"), "year_from")
```

```python
@pytest.mark.spec("CAT-007", "CAT-008", "CAT-001", "CAT-002")
def test_filters_combine_with_keyword_and_category(client):
    assert ids(client.get("/books?available=true&category=cs")) == ["B001", "B003", "B005"]
    assert ids(client.get("/books?available=true&q=python")) == ["B001"]
    assert ids(client.get("/books?available=false&category=lit")) == ["B007", "B009"]
    assert ids(client.get("/books?available=true&year_from=2000&year_to=2015")) == ["B003", "B014", "B016"]
```

```python
@pytest.mark.spec("CAT-007", "CAT-004")
def test_filters_apply_before_pagination(client):
    first = client.get("/books?available=true&page_size=4")
    assert first.json["total"] == 9
    assert ids(first) == ["B001", "B003", "B005", "B006"]
    last = client.get("/books?available=true&page_size=4&page=3")
    assert last.json["total"] == 9
    assert ids(last) == ["B016"]
```

```python
@pytest.mark.spec("CAT-007", "CAT-003")
def test_filters_apply_before_sorting(client):
    response = client.get("/books?available=false&sort=-year&page_size=50")
    assert ids(response) == ["B004", "B002", "B012", "B009", "B015", "B013", "B007"]
```

```python
@pytest.mark.spec("CAT-007", "DATA-001", "LOAN-001", "LOAN-004")
def test_available_filter_follows_loans_and_returns(client):
    loan = client.post("/loans", {"member_id": "M002", "copy_id": "C021"}).json["loan"]  # B016 唯一的副本
    assert "B016" not in ids(client.get("/books?available=true&page_size=50"))
    assert "B016" in ids(client.get("/books?available=false&page_size=50"))
    client.post(f"/loans/{loan['id']}/return")
    assert "B016" in ids(client.get("/books?available=true&page_size=50"))
```

### 3.2 相关回归测试（必须保持通过）

- `tests/test_api_books.py`：11 个测试函数，验证 API-002, API-004, CAT-001, CAT-002, CAT-003, CAT-004, DATA-001
- `tests/test_api_loans.py`：5 个测试函数，验证 API-002, API-003
- `tests/test_api_params.py`：8 个测试函数，验证 API-002, API-003, API-004
- `tests/test_catalog_search.py`：12 个测试函数，验证 CAT-001, CAT-002, CAT-003, CAT-004, CAT-006, DATA-001
- `tests/test_loans.py`：2 个测试函数，验证 DATA-001

相关回归：`python -m pytest -q tests/test_api_books.py tests/test_api_loans.py tests/test_api_params.py tests/test_catalog_search.py tests/test_loans.py`；完整回归（全部非目标测试）：`python -m pytest -q` 并排除目标测试。

## 4. 任务状态（PowerContext）

- Scope：`sddctx/campus-library/T-101`（scp_7h98ahj80qfgxwycknkmnjqth0），已有记录 3 条
- 最近一次记录：partial — 修改前验证（工程指纹 8acd5172039b）：目标测试 25 个用例失败 25 个（断言失败 25）；回归测试 91 passed
- 已完成：
  - 生成任务上下文（seekdb 导入批次 #1，上下文 sha256 2a7743ee4a9e）：目标规格 CAT-007, CAT-008；约束 API-002, API-003, API-004, CAT-002, CAT-003, CAT-004, DATA-001；需要修改 library/api/handlers.py::list_books, library/catalog.py::search_books；目标测试 15 个测试函数；相关回归测试文件 5 个
  - 修改前验证（工程指纹 8acd5172039b）：目标测试 25 个用例失败 25 个（断言失败 25）；回归测试 91 passed
- 已有验证结果：
  - 上下文来源核对：**passed** — 上下文引用的 81 处来源与工程文件逐行比对，一致 81 处
  - 修改前目标测试因功能未实现而失败：**passed** — 25 个用例中失败 25 个，其中断言失败 25 个；环境类问题（导入、夹具、收集错误）0 个；退出码 1；日志 runs/T-101/tests/before/target.log
  - 修改前回归测试全部通过：**passed** — 91 passed, 0 failed，exit 0；日志 runs/T-101/tests/before/regression.log
- 待办：
  - 把上下文交给 MiniMax 开发助手完成代码修改（sddctx develop）
  - 修改后验证：目标测试与回归测试应全部通过（sddctx verify --phase after）
- 下一步：develop

## 5. 工程约定

来源 `specs/README.md:1-3`：

```markdown
# 规格约定

本目录是校园图书馆借阅服务（campus-library）的有效规格。开发遵循规格驱动开发（SDD）：先写规格条目和验收测试，再改代码。
```

来源 `specs/README.md:5-13`：

```markdown
## 条目格式

- 一级标题是规格文档（能力域），二级标题是能力分组（通常对应一个接口），三级标题是需求条目：`### <ID> <标题>`。
- ID 由大写前缀和三位序号组成，例如 `CAT-007`。前缀：`CAT` 馆藏检索、`DATA` 数据模型、`LOAN` 借还、`FINE` 罚款、`API` 接口约定。
- 条目标题下的列表是元数据：
  - `状态`：`已实现`、`待实现` 或 `已废弃`。`待实现` 表示规格和验收测试已经写好，代码还没有实现。
  - `接口`：涉及的 HTTP 接口。
  - `关联`：本条目引用的其他条目。
- 正文写行为和约束；`验收：` 之后的列表是可测试的验收标准。
```

来源 `specs/README.md:15-20`：

```markdown
## 追溯关系

- 代码在 docstring 中用 `实现: CAT-001, CAT-002` 标注它实现了哪些条目。
- 测试用 `@pytest.mark.spec("CAT-001")` 标注它验证哪些条目（也可以在模块级写 `pytestmark`）。
- `待实现` 条目的测试是本次开发的目标测试，修改前应当失败；其余测试是回归测试，必须保持通过。
- 只有规格的维护者可以修改 `specs/` 和 `tests/`，实现者只修改 `library/` 下的代码。
```

## 附：seekdb 检索结果

| 检索 | 片段 | RRF | 全文名次 | 向量名次 |
|---|---|---|---|---|
| 规格 | `spec:CAT-008` | 0.0325 | 2 | 1 |
| 规格 | `spec:CAT-007` | 0.032 | 3 | 2 |
| 规格 | `spec:CAT-002` | 0.0301 | 6 | 7 |
| 规格 | `spec:CAT-003` | 0.0292 | 15 | 3 |
| 规格 | `spec:LOAN-001` | 0.029 | 12 | 6 |
| 规格 | `spec:CAT-006` | 0.0284 | 11 | 10 |
| 规格 | `spec:API-001` | 0.028 | 19 | 5 |
| 规格 | `spec:CAT-005` | 0.0278 | 13 | 11 |
| 规格 | `spec:LOAN-006` | 0.0277 | 17 | 8 |
| 规格 | `spec:LOAN-003` | 0.0277 | 23 | 4 |
| 规格 | `spec:CAT-004` | 0.027 | 16 | 12 |
| 规格 | `spec:LOAN-005` | 0.0267 | 22 | 9 |
| 代码 | `code:library/api/params.py` | 0.0311 | 8 | 1 |
| 代码 | `code:library/catalog.py::available_copies` | 0.0311 | 2 | 7 |
| 代码 | `code:library/fines.py::overdue_fine_cents` | 0.03 | 11 | 3 |
| 代码 | `code:library/api/params.py::parse_bool` | 0.0297 | 10 | 5 |
| 代码 | `code:library/api/handlers.py::list_books` | 0.0294 | 6 | 10 |
| 代码 | `code:library/loans.py::borrow` | 0.028 | 15 | 8 |
| 代码 | `code:library/__init__.py` | 0.0278 | 26 | 2 |
| 代码 | `code:library/loans.py::return_copy` | 0.0274 | 14 | 12 |
| 代码 | `code:library/api/app.py::LibraryApp` | 0.0267 | 30 | 4 |
| 代码 | `code:library/loans.py::renew` | 0.0261 | 31 | 6 |
| 代码 | `code:library/api/__main__.py::main` | 0.0259 | 28 | 9 |
| 代码 | `code:library/api/app.py::parse_query` | 0.0239 | 42 | 11 |

````

</details>
