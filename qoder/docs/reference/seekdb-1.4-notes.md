# seekdb 1.4 混合检索备忘（产品负责人整理）

> 整理自团队此前在 seekdb v1.4.0（镜像 `oceanbase/seekdb:1.4.0-100000172026082615`，`SELECT version()` 返回
> `5.7.25-OceanBase seekdb-v1.4.0.0`）上的实测，作为 Qoder 开发时的输入材料。

## 连接

- MySQL 协议，容器内端口 2881，用户 `root`，密码由镜像环境变量 `ROOT_PASSWORD` 设置。任意 MySQL 驱动可用（Python 用 PyMySQL）。
- 容器首次启动要几十秒才接受连接，用 `mysql -h127.0.0.1 -P2881 -uroot -p... -e 'SELECT 1'` 做健康检查。

## 建表：向量 + 全文 + 结构化过滤在同一张表

```sql
CREATE TABLE chunks (
  id        BIGINT PRIMARY KEY,
  course_id VARCHAR(64),
  doc_kind  VARCHAR(16),            -- notes / slides / exam / paper
  content   TEXT,
  embedding VECTOR(512),
  VECTOR INDEX idx_emb (embedding) WITH (distance=cosine, type=hnsw, sync_mode=immediate),
  FULLTEXT INDEX ft_content (content) WITH PARSER ik
) ORGANIZATION HEAP;
```

- `DBMS_HYBRID_SEARCH` 要求 **`ORGANIZATION HEAP`**（默认的索引组织表 + 用户主键会报 `table with user provided primary key not supported`）。
- 堆表上的 HNSW 索引默认 `SYNC_MODE=ASYNC`，刚写入的行要几秒后才能被向量检索到；加 **`sync_mode=immediate`** 写完即可搜。
- 中文全文索引用 **`WITH PARSER ik`**（不写会把整串中文当一个词）。`ik` 默认 smart 模式切得粗（"文献检索"是一个词），需要更高召回时用
  `WITH PARSER ik PARSER_PROPERTIES=(ik_mode="max_word")`。`SELECT tokenize('文本', 'ik')` 可查看分词。英文文本在 ik 下也能正常分词。
- 向量以字符串 `'[0.1,0.2,...]'` 写入，维度必须与列定义一致。

## 一条语句完成混合检索：DBMS_HYBRID_SEARCH.SEARCH

```sql
SELECT DBMS_HYBRID_SEARCH.SEARCH('chunks', '{
  "query": {"bool": {"must": [{"match": {"content": "事务隔离级别"}}],
                     "filter": [{"term": {"course_id": "db101"}}, {"terms": {"doc_kind": ["notes", "slides"]}}]}},
  "knn": {"field": "embedding", "k": 20, "query_vector": [ ... ],
          "filter": [{"term": {"course_id": "db101"}}, {"terms": {"doc_kind": ["notes", "slides"]}}]},
  "rank": {"rrf": {}},
  "_source": ["id", "content", "_keyword_score", "_semantic_score", "_keyword_rank", "_semantic_rank"],
  "size": 10
}') AS hits;
```

- 返回 JSON 数组（PyMySQL 拿到的是字符串，需要 `json.loads`），每个元素含 `_source` 指定的列和 `_score`，按 `_score` 降序；**没有命中时返回 NULL**。
- RRF 分数 = Σ 1/(该路排名 + 60)。`_keyword_rank` / `_semantic_rank` 只在 `rank.rrf` 下可用；`_keyword_score`（BM25）和
  `_semantic_score`（cosine 索引为 `1 - 距离/2`）两种模式都能取。RRF 只反映相对排名，要判断"证据够不够强"请看这两个原始分数。
- **过滤条件要在 `query` 和 `knn` 两个分支里分别写**，只写一边的话另一路会带回不该有的行。
- **转义**：`match` 文本和过滤值会被原样拼进生成的 SQL，含 `'` `"` `\` 就会报 `ERROR 1064`。拼 JSON 前去掉用户文本里的引号和反斜杠；
  过滤值只用受控的 id。整个 JSON 用参数绑定传入：`cursor.execute("SELECT DBMS_HYBRID_SEARCH.SEARCH('chunks', %s)", (json_text,))`。
- `DBMS_HYBRID_SEARCH.GET_SQL(表名, 同样的 JSON)` 返回它生成的 SQL，可以拿来 `EXPLAIN` 或展示给用户看"seekdb 实际执行了什么"。
- `size` 默认 10；`rank_window_size` 不能小于 `size`。

## 单路检索（需要时）

```sql
-- 向量 ANN：距离函数必须和索引 distance 对应（cosine → cosine_distance），否则退化成全表扫描
SELECT id, cosine_distance(embedding, '[...]') AS dist FROM chunks ORDER BY dist APPROXIMATE LIMIT 10;
-- 全文：自然语言模式按 BM25 打分
SELECT id, MATCH(content) AGAINST('两阶段锁') AS s FROM chunks WHERE MATCH(content) AGAINST('两阶段锁') ORDER BY s DESC LIMIT 10;
```
