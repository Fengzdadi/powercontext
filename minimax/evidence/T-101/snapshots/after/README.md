# campus-library：校园图书馆借阅服务

本作品的业务工程，为本题原创编写（Apache-2.0），不含第三方代码。它是一个只依赖 Python 标准库的小型 HTTP 服务：

- 馆藏检索与详情：`GET /books`、`GET /books/{book_id}`
- 借书、还书、续借：`POST /loans`、`POST /loans/{loan_id}/return`、`POST /loans/{loan_id}/renew`
- 读者借阅记录：`GET /members/{member_id}/loans`

数据在内存中，启动时从 `library/data/seed.json` 载入（16 本书、21 个副本、5 位读者、9 笔借阅）。

## 目录

| 路径 | 内容 |
|---|---|
| `specs/` | 有效规格（SDD）。条目格式和追溯约定见 `specs/README.md` |
| `library/` | 业务代码。docstring 中的 `实现: <ID>` 标注实现了哪些规格条目 |
| `tests/` | pytest 测试。`@pytest.mark.spec(<ID>)` 标注验证哪些规格条目 |

## 运行

```bash
python -m pytest -q                       # 需要 Python ≥ 3.11 和 pytest
python -m library.api --port 18908        # 启动服务后：curl 'http://127.0.0.1:18908/books?q=python'
```

`specs/catalog.md` 中的 CAT-007（可借状态筛选）和 CAT-008（出版年份区间筛选）是“待实现”条目，
`tests/test_api_books_filters.py` 是它们的验收测试，在实现之前这些测试会失败。
