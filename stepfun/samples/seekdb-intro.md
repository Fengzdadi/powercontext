seekdb 是 OceanBase 推出的 AI 原生搜索数据库，以 Apache 2.0 协议开源。它在一个引擎里同时提供关系表、向量检索、全文检索、JSON 与标量过滤能力，应用可以用一条 SQL 或一次函数调用完成“关键词 + 语义”的混合检索，而不必维护多套系统再在应用层拼接结果。

seekdb 兼容 MySQL 协议，既可以作为独立的 server 部署，也可以通过 seekdb-js、pyseekdb 等 SDK 以嵌入式方式运行。向量列使用 VECTOR(n) 类型，支持 HNSW 等索引；全文索引支持 IK、ngram 等分词器，适合中文场景。混合检索由 DBMS_HYBRID_SEARCH 包在数据库内部完成，支持 RRF 等融合排序方式。
