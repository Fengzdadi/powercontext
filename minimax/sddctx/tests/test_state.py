import json

from sddctx.state import STATE_PREFIX, load_state, write_contract, write_outcome


class FakePowerContext:
    """内存里的 PowerContext：只实现 sddctx 用到的几个接口。"""

    def __init__(self):
        self.scopes, self.items = {}, {}

    def find_scope(self, title):
        return self.scopes.get(title)

    def ensure_scope(self, title, summary):
        return self.scopes.setdefault(title, f"scp_{len(self.scopes) + 1}")

    def _append(self, scope_id, source_id, doc):
        items = self.items.setdefault(scope_id, [])
        items.append({"source_id": source_id, "position": len(items) + 1, "content": json.dumps(doc, ensure_ascii=False)})
        return {"position": len(items)}

    def record_contract(self, scope_id, source_id, contract):
        return self._append(scope_id, source_id, contract)

    def record_outcome(self, scope_id, source_id, outcome):
        for claim in outcome["observations"]:
            assert len(claim["text"]) <= 8192
        return self._append(scope_id, source_id, outcome)

    def sources(self, scope_id):
        return list(self.items.get(scope_id, []))


def test_state_round_trip_with_large_machine_state():
    pc = FakePowerContext()
    state = load_state(pc, "demo", "T-1")
    assert state.empty and state.scope_id is None
    write_contract(pc, state, "目标", ["事实"], ["范围"], ["排除"], ["标准"], ["说明"])
    big = {"steps_done": ["context"], "target_tests": [f"tests/test_x.py::test_{i:04d}_" + "x" * 60 for i in range(400)]}
    write_outcome(pc, state, step="context", status="partial", summary="摘要", objective="目标",
                  done=["生成上下文"], checks=[{"name": "核对", "status": "passed", "details": "一致"}], todo=["下一步"], machine=big)  # fmt: skip
    parts = [c for c in json.loads(pc.items["scp_1"][1]["content"])["observations"] if c["text"].startswith(STATE_PREFIX)]
    assert len(parts) > 1  # 机器可读状态超过单条上限，被拆成多段

    reloaded = load_state(pc, "demo", "T-1")
    assert reloaded.scope_id == "scp_1" and len(reloaded.contracts) == 1
    assert reloaded.steps_done == ["context"]
    assert reloaded.machine["target_tests"] == big["target_tests"]
    assert reloaded.latest.observations == ["生成上下文"]
    assert reloaded.latest.checks[0]["status"] == "passed"
    assert reloaded.latest.step == "context"
