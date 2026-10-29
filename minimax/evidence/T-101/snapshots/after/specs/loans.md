# 借还（loans）

## 借阅 `POST /loans`

### LOAN-001 借阅前置条件
- 状态：已实现
- 接口：POST /loans
- 关联：API-002, DATA-001, DATA-003

请求体为 `{"member_id": 读者编号, "copy_id": 副本编号}`，两个字段都必须是非空字符串，否则返回 400 `invalid_parameter`，`field` 为字段名。读者或副本不存在时返回 404 `not_found`；读者账户停用时返回 409 `member_inactive`；副本不是 `on_shelf` 时返回 409 `copy_unavailable`。借阅成功返回 201 和新借阅记录，副本变为 `on_loan`。

验收：
- 停用读者借书返回 409 `member_inactive`。
- 借一个已借出的副本返回 409 `copy_unavailable`。

### LOAN-002 借阅数量上限
- 状态：已实现
- 接口：POST /loans
- 关联：DATA-003

读者未归还的借阅数达到上限后不能再借：学生 5 本，教职工 10 本。超限返回 409 `loan_limit_reached`。

验收：
- 已有 5 本未还图书的学生再借一本，返回 409 `loan_limit_reached`。

### LOAN-003 借期
- 状态：已实现
- 接口：POST /loans
- 关联：DATA-003

借期按读者类型确定：学生 30 天，教职工 60 天。`due_on` 等于借阅日期加借期天数。

验收：
- 学生 2026-10-15 借书，`due_on` 为 2026-11-14。

## 归还 `POST /loans/{loan_id}/return`

### LOAN-004 归还
- 状态：已实现
- 接口：POST /loans/{loan_id}/return
- 关联：FINE-001, FINE-003

归还时记录 `returned_on` 为当天，副本恢复为 `on_shelf`，响应为 `{"loan": 借阅记录, "fine_cents": 罚款}`。借阅记录不存在返回 404 `not_found`；已经归还的借阅再次归还返回 409 `already_returned`。

验收：
- 逾期 3 天归还，`fine_cents` 为 150。

## 续借 `POST /loans/{loan_id}/renew`

### LOAN-005 续借
- 状态：已实现
- 接口：POST /loans/{loan_id}/renew
- 关联：LOAN-003

每笔借阅最多续借 2 次，每次从当前 `due_on` 起再延长一个借期（LOAN-003）。已逾期（当天晚于 `due_on`）不能续借，返回 409 `loan_overdue`；已归还的借阅返回 409 `already_returned`；超过续借次数返回 409 `renewal_limit_reached`。

验收：
- 第 3 次续借返回 409 `renewal_limit_reached`。

## 读者借阅记录 `GET /members/{member_id}/loans`

### LOAN-006 借阅记录查询
- 状态：已实现
- 接口：GET /members/{member_id}/loans?include_returned=
- 关联：API-003

默认只返回读者未归还的借阅；布尔参数 `include_returned`（按 API-003 解析）为真时同时返回已归还的借阅。结果按借阅日期降序排列，同一天按借阅编号升序。读者不存在返回 404 `not_found`。

验收：
- `include_returned=1` 时包含已归还的借阅。
- `include_returned=maybe` 返回 400 `invalid_parameter`，`field` 为 `include_returned`。
