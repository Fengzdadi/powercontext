from sddctx.workspace import copy_tree, diff_trees, glob_match, is_read_only, tree_sha


def test_glob_match_follows_manifest_semantics():
    assert glob_match("library/catalog.py", "library/**/*.py")
    assert glob_match("library/api/params.py", "library/**/*.py")
    assert not glob_match("conftest.py", "library/**/*.py")
    assert glob_match("tests/sub/test_x.py", "tests/**")
    assert not glob_match("specs/a/b.md", "specs/*.md")
    assert is_read_only("sdd.toml", ["specs/**", "sdd.toml"])
    assert not is_read_only("library/catalog.py", ["specs/**", "tests/**"])


def test_diff_and_fingerprint(tmp_path, project_dir):
    before = copy_tree(project_dir, tmp_path / "before")
    after = copy_tree(before, tmp_path / "after")
    assert diff_trees(before, after) == ""
    target = after / "library" / "clock.py"
    target.write_text(target.read_text(encoding="utf-8") + "# 新增一行\n", encoding="utf-8")
    diff = diff_trees(before, after)
    assert diff.startswith("diff --git a/library/clock.py b/library/clock.py")
    assert "+# 新增一行" in diff
    assert tree_sha(before, ["tests/**"]) == tree_sha(after, ["tests/**"])
    assert tree_sha(before) != tree_sha(after)
