# 数据模型（data）

## 馆藏副本

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

## 图书

### DATA-002 图书字段
- 状态：已实现
- 关联：CAT-005

图书字段：`id`（如 `B001`）、`isbn`、`title`、`author`、`category`（分类代码）、`year`（出版年份，整数）、`price_cents`（定价，单位为分，整数）。

验收：
- 种子数据中每本书的 `year` 和 `price_cents` 都是整数。

## 读者

### DATA-003 读者类型与状态
- 状态：已实现
- 关联：LOAN-001, LOAN-002, LOAN-003

读者字段：`id`（如 `M001`）、`name`、`kind`（`student` 学生或 `staff` 教职工）、`active`（账户是否正常）。
