# 馆藏检索与详情（catalog）

读者通过检索接口查找馆藏图书，通过详情接口查看某本书的副本情况。

## 图书检索 `GET /books`

### CAT-001 关键词检索
- 状态：已实现
- 接口：GET /books?q=
- 关联：API-005

参数 `q` 对书名和作者做子串匹配，不区分大小写，忽略前后空白。`q` 为空或只有空白时视为没有提供。

验收：
- `q=python` 返回书名或作者包含 “python”（不区分大小写）的图书。
- `q=%20%20` 与不带 `q` 的结果相同。

### CAT-002 分类筛选
- 状态：已实现
- 接口：GET /books?category=
- 关联：API-002

参数 `category` 按分类代码精确匹配，馆藏分类代码为 `cs`（计算机）、`lit`（文学）、`hist`（历史）、`math`（数学）。馆藏中不存在的分类返回 400，错误码 `invalid_parameter`，`field` 为 `category`。

验收：
- `category=hist` 只返回历史类图书。
- `category=music` 返回 400 `invalid_parameter`，`field` 为 `category`。

### CAT-003 排序
- 状态：已实现
- 接口：GET /books?sort=
- 关联：API-002

参数 `sort` 取值：`id`（默认，按图书编号升序）、`title`（按书名的 Unicode 码位升序）、`year`（按出版年份升序）、`-year`（按出版年份降序）。排序键相同的图书按图书编号升序，保证结果稳定。其他取值返回 400 `invalid_parameter`，`field` 为 `sort`。

验收：
- `sort=-year` 时出版年份大的在前，同年份按编号升序。
- `sort=price` 返回 400 `invalid_parameter`。

### CAT-004 分页
- 状态：已实现
- 接口：GET /books?page=&page_size=
- 关联：API-004

`page` 默认 1，`page_size` 默认 10、最大 50，二者都必须是正整数，否则返回 400 `invalid_parameter`，`field` 为对应参数名。响应为 `{"total": 符合条件的图书总数, "page": 当前页, "page_size": 每页条数, "items": [...]}`。所有筛选条件都在排序和分页之前生效，`total` 是筛选后的总数。页码超出末页时返回空的 `items`，`total` 不变。

验收：
- 共 16 本书时，`page=2&page_size=10` 返回 6 条，`total` 为 16。
- `page_size=51` 返回 400 `invalid_parameter`，`field` 为 `page_size`。

### CAT-006 检索结果条目
- 状态：已实现
- 接口：GET /books
- 关联：DATA-001

`items` 中每个条目包含 `id`、`title`、`author`、`category`、`year`、`copies_available`。`copies_available` 是该书在架副本的数量（见 DATA-001）。

验收：
- 所有副本都已借出的图书，`copies_available` 为 0。

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

### CAT-008 出版年份区间筛选
- 状态：待实现
- 接口：GET /books?year_from=&year_to=
- 关联：API-002, API-004, CAT-004

新增整数参数 `year_from`、`year_to`（按 API-004 解析），表示出版年份的闭区间 `[year_from, year_to]`，两个参数可以只提供一个。参数不是整数时返回 400 `invalid_parameter`，`field` 为对应参数名；同时提供且 `year_from` 大于 `year_to` 时返回 400 `invalid_parameter`，`field` 为 `year_from`。年份筛选同样可以和其他条件组合，并在分页之前生效（CAT-004）。

验收：
- `year_from=2000&year_to=2015` 包含 2000 年和 2015 年出版的图书。
- 只给 `year_to=1950` 时返回 1950 年及以前出版的图书。
- `year_from=2020&year_to=2010` 返回 400 `invalid_parameter`，`field` 为 `year_from`。

## 图书详情 `GET /books/{book_id}`

### CAT-005 图书详情
- 状态：已实现
- 接口：GET /books/{book_id}
- 关联：API-002, DATA-001

返回图书的全部字段（`id`、`isbn`、`title`、`author`、`category`、`year`、`price_cents`），以及 `copies_total`（副本总数）、`copies_available`（在架副本数）和副本列表 `copies`（每项含 `id`、`barcode`、`status`）。图书不存在时返回 404，错误码 `not_found`。

验收：
- `GET /books/B002` 的 `copies_total` 为 2，`copies_available` 为 0。
- `GET /books/B999` 返回 404 `not_found`。
