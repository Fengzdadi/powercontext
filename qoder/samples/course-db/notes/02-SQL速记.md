# 第2章 SQL（速记，没整理完）

> 2026 秋《数据库系统原理》第 3 周。这一章课上主要在机房做练习，笔记记得不多。

## 基本查询

- `SELECT 列 FROM 表 WHERE 条件`，`DISTINCT` 去重。
- `ORDER BY 列 DESC` 降序排列。
- 多表查询用 `JOIN ... ON ...`，外连接分 `LEFT JOIN` / `RIGHT JOIN`。

## 分组

- `GROUP BY` 分组后配合聚集函数 `COUNT`、`SUM`、`AVG`、`MAX`、`MIN`。
- 对分组结果再筛选用 `HAVING`，不能用 `WHERE`。

（嵌套子查询那节没跟上，等期末前补。）
