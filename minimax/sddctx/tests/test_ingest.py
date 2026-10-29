from sddctx import ingest


def test_chunks_cover_project_and_match_file_lines(project_dir):
    manifest, chunks = ingest.collect(project_dir)
    kinds = {}
    for chunk in chunks:
        kinds[chunk.kind] = kinds.get(chunk.kind, 0) + 1
        lines = (project_dir / chunk.path).read_text(encoding="utf-8").splitlines()
        assert "\n".join(lines[chunk.start_line - 1 : chunk.end_line]) == chunk.content, chunk.chunk_id
    assert manifest["project"]["id"] == "campus-library"
    assert kinds["spec"] == 25 and kinds["test"] > 0 and kinds["code"] > 0


def test_traceability_links(project_dir):
    _, chunks = ingest.collect(project_dir)
    by_id = {c.chunk_id: c for c in chunks}
    cat7 = by_id["spec:CAT-007"]
    assert cat7.status == "待实现"
    assert set(cat7.targets("references")) == {"API-002", "API-003", "DATA-001", "CAT-004"}
    assert set(by_id["code:library/catalog.py::search_books"].targets("implements")) == {"CAT-001", "CAT-002", "CAT-003", "CAT-004"}
    test = by_id["test:tests/test_api_books_filters.py::test_year_range_is_inclusive"]
    assert "CAT-008" in test.targets("verifies")


def test_content_sha_changes_with_content(project_dir):
    _, chunks = ingest.collect(project_dir)
    chunk = next(c for c in chunks if c.chunk_id == "spec:CAT-007")
    before = chunk.content_sha
    chunk.content += "\n- 新增一条验收。"
    assert chunk.content_sha != before
