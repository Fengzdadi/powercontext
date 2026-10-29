from sddctx.agent import Workspace, replay_session
from sddctx.workspace import copy_tree, diff_trees

READ_ONLY = ["specs/**", "tests/**", "sdd.toml", "pyproject.toml"]
WRITABLE = ["library/**/*.py"]


def test_tools_guard_read_only_and_out_of_scope_paths(tmp_path, project_dir):
    ws = Workspace(copy_tree(project_dir, tmp_path / "ws"), READ_ONLY, WRITABLE, test_runner=None)
    ok, message, meta = ws.execute("write_file", {"path": "tests/test_extra.py", "content": "x"})
    assert not ok and meta == {"rejected": "read_only"} and "只读" in message
    ok, _, _ = ws.execute("write_file", {"path": "conftest.py", "content": "x"})
    assert not ok
    ok, message, _ = ws.execute("read_file", {"path": "../outside.txt"})
    assert not ok and "越界" in message


def test_edit_file_requires_unique_match_and_replay_reproduces_diff(tmp_path, project_dir):
    base = copy_tree(project_dir, tmp_path / "base")
    ws = Workspace(copy_tree(base, tmp_path / "ws"), READ_ONLY, WRITABLE, test_runner=None)
    ok, message, _ = ws.execute("edit_file", {"path": "library/clock.py", "old_text": "no such text", "new_text": "x"})
    assert not ok and "没有找到" in message
    text = (ws.root / "library/clock.py").read_text(encoding="utf-8")
    first_line = text.splitlines()[0]
    args = {"path": "library/clock.py", "old_text": first_line, "new_text": first_line + "  # 已修改"}
    ok, _, meta = ws.execute("edit_file", args)
    assert ok
    diff = diff_trees(base, ws.root)

    session = {"turns": [{"turn": 1, "tool_results": [{"name": "edit_file", "input": args, "ok": True, "meta": meta}]}]}
    replay = Workspace(copy_tree(base, tmp_path / "replay"), READ_ONLY, WRITABLE, test_runner=None)
    log = replay_session(session, replay)
    assert log[0]["after_sha_matches"]
    assert diff_trees(base, replay.root) == diff
