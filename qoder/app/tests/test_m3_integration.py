"""M3 集成测试：对运行中的真实 PowerContext（127.0.0.1:18801）。

Run with: export EXAMRADAR_IT=1 && uv run pytest -m integration

不需要 seekdb 数据；学习者在 PC 里按运行随机命名，避免跨运行污染。
"""
import uuid

import pytest

from examradar.mastery import MasteryState, format_mastery_text, parse_mastery_text
from examradar.pc_client import (
    PowerContextClient, PowerContextUnavailable, bootstrap_opening_line,
    parse_prepared_content, recent_calls,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def pc():
    return PowerContextClient()


@pytest.fixture(scope="module")
def scope_id(pc):
    learner = f"it-同学-{uuid.uuid4().hex[:6]}"
    sid = pc.ensure_scope(learner, "db101_it")
    # 幂等：重复创建返回同一个 Scope
    assert pc.ensure_scope(learner, "db101_it") == sid
    return sid


class TestMemoryLifecycle:
    def test_mastery_card_revisions(self, pc, scope_id):
        state = MasteryState(topic_id="t08", topic_name="隔离级别与 MVCC",
                             box=1, correct=0, wrong=1)
        aid, rev = pc.create_memory(scope_id, "mastery", format_mastery_text(state))
        assert rev == 1
        pc.put_tags(scope_id, aid, ["examradar", "type-mastery", "topic-t08"])
        pc.set_handle(scope_id, "mastery-t08", aid, rev)

        got = pc.get_handle(scope_id, "mastery-t08")
        assert got["artifact_id"] == aid

        state2 = state.apply_answer(True)
        rev2 = pc.replace_memory(scope_id, aid, "mastery",
                                 format_mastery_text(state2))
        assert rev2 == 2

        text, cur_rev = pc.get_memory(scope_id, aid)
        parsed = parse_mastery_text(text)
        assert parsed.box == 2 and parsed.correct == 1
        assert cur_rev == 2

        revs = pc.get_revisions(scope_id, aid)
        assert [r["revision"] for r in revs] == [1, 2]
        assert "盒 1" in revs[0]["text"] and "盒 2" in revs[1]["text"]

        items = pc.query_by_tags(scope_id, ["type-mastery", "topic-t08"],
                                 families=["atomic-memory"])
        assert any(i["reference"]["artifact_id"] == aid for i in items)

    def test_bootstrap_returns_latest_revision(self, pc, scope_id):
        pc.remember(scope_id, "mistake",
                    "【错题】t08 隔离级别与 MVCC：你的回答「锁」，"
                    "正确答案「多版本并发控制」，出处 05-事务与并发控制.md")
        aid, rev = pc.create_memory(scope_id, "plan", "上次你在『X』上错了 1 次")
        pc.put_tags(scope_id, aid, ["examradar", "type-plan", "bootstrap-context"])
        pc.set_handle(scope_id, "review-plan", aid, rev)
        # 替换后 bootstrap 必须带回最新 revision
        pc.replace_memory(scope_id, aid, "plan",
                          "上次你在『隔离级别与 MVCC』上错了 1 次，先复习它")

        out = pc.bootstrap(scope_id, event_id=f"it-{uuid.uuid4().hex[:8]}")
        assert out["status"] == "ready"
        match = [i for i in out["items"]
                 if (i.get("artifact") or {}).get("artifact_id") == aid]
        assert match, "bootstrap 没带回复习计划"
        assert match[0]["artifact"]["revision"] == 2

    def test_prepare_recalls_mistake_by_topic_id_and_name(self, pc, scope_id):
        out = pc.prepare(scope_id, "t08 隔离级别与 MVCC")
        assert out["status"] in ("ready", "empty")
        if out["status"] == "ready":
            items = parse_prepared_content(out["content"])
            texts = [i["text"] for i in items]
            assert any("t08" in t and "【错题】" in t for t in texts)

    def test_call_log_records_real_calls(self):
        calls = recent_calls(10)
        assert calls
        assert all("path" in c for c in calls)


class TestDegradation:
    def test_dead_port_raises_unavailable(self):
        client = PowerContextClient(base_url="http://127.0.0.1:18803",
                                    timeout=2.0)
        with pytest.raises(PowerContextUnavailable):
            client.ensure_scope("降级同学", "db101")
        ok, detail = client.health()
        assert ok is False

    def test_unavailable_opening_line_is_none(self):
        assert bootstrap_opening_line(None) is None
        assert bootstrap_opening_line({"status": "empty"}) is None
