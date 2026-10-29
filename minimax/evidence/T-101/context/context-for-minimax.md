# 任务上下文：T-101 图书检索增加可借状态和出版年份筛选

> 工程 `campus-library`；资料来自 seekdb 导入批次 #1（161 个片段，工程目录指纹 `8acd5172039b`，代码版本 `f94b65358bb9`）。引用的来源 81 处，逐行核对一致 81 处。

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

- Scope：`sddctx/campus-library/T-101`（scp_2tjzbxszf0g05wwpsqkkvp1hxb），已有记录 3 条
- 最近一次记录：partial — 修改前验证（工程指纹 8acd5172039b）：目标测试 25 个用例失败 25 个（断言失败 25）；回归测试 91 passed
- 已完成：
  - 生成任务上下文（seekdb 导入批次 #1，上下文 sha256 d8ab69aefe74）：目标规格 CAT-007, CAT-008；约束 API-002, API-003, API-004, CAT-002, CAT-003, CAT-004, DATA-001；需要修改 library/api/handlers.py::list_books, library/catalog.py::search_books；目标测试 15 个测试函数；相关回归测试文件 5 个
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
