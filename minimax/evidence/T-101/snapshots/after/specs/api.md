# HTTP 接口约定（api）

所有接口共同遵守的约定。各接口的业务规则见对应的规格文档。

## 响应与错误

### API-001 JSON 响应
- 状态：已实现

所有响应的 `Content-Type` 为 `application/json; charset=utf-8`。查询成功返回 200，创建成功返回 201。未匹配到路由的请求返回 404 `not_found`。

验收：
- `GET /books` 的响应头 `Content-Type` 为 `application/json; charset=utf-8`。

### API-002 错误格式
- 状态：已实现
- 关联：API-001

错误响应体为 `{"error": {"code": 错误码, "message": 说明, "field": 出错的参数名或 null}}`。

- 查询参数或请求体不合法：400，错误码 `invalid_parameter`，`field` 为参数名；
- 资源不存在：404，错误码 `not_found`，`field` 为 null；
- 违反业务规则：409，使用具体的错误码（例如 `loan_limit_reached`），`field` 为 null。

验收：
- `GET /books?page=0` 返回 400，响应体 `error.code` 为 `invalid_parameter`，`error.field` 为 `page`。

## 查询参数

### API-003 布尔查询参数
- 状态：已实现
- 关联：API-002

布尔查询参数接受 `true`、`false`、`1`、`0`，不区分大小写，忽略前后空白；`true`、`1` 为真，`false`、`0` 为假。参数出现但取值不在上述范围（包括空字符串）时返回 400 `invalid_parameter`，`field` 为参数名。参数没有出现时由各接口决定默认行为。

验收：
- `include_returned=True` 与 `include_returned=1` 等价。
- `include_returned=yes` 返回 400 `invalid_parameter`，`field` 为 `include_returned`。

### API-004 整数查询参数
- 状态：已实现
- 关联：API-002

整数查询参数只接受十进制 ASCII 数字，可以带一个正负号，忽略前后空白（例如 `" 7 "`、`"+3"`、`"-2"`）。不是整数时（例如 `"abc"`、`"1.5"`、`"1_000"`、空字符串）返回 400 `invalid_parameter`，`field` 为参数名。取值范围由各接口规定，超出范围同样返回 400 `invalid_parameter`。

验收：
- `page=abc` 返回 400 `invalid_parameter`，`field` 为 `page`。

### API-005 未声明的查询参数
- 状态：已实现
- 关联：API-001

接口忽略没有声明的查询参数，以保持向前兼容：带上未知参数的请求与不带它时结果相同。同名参数出现多次时只取第一个值。

验收：
- `GET /books?foo=bar` 与 `GET /books` 结果相同。
