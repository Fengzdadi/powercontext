"""根据任务从 seekdb 选出规格、代码和测试，结合 PowerContext 中的任务状态生成开发上下文。

选择过程（每一步都是对 seekdb 的真实查询，结果写进查询记录）：
1. 规格：用任务文本做一次混合检索（DBMS_HYBRID_SEARCH，IK 全文 + 向量，RRF 融合），取强命中；
   其中状态为“待实现”的条目是本次要实现的目标，其余命中是约束。任务文本里直接写出的规格 ID 也算命中。
2. 扩展：目标条目引用的条目（sdd_links.references）是必须遵守的约束；与目标同一能力分组（同一接口）
   的已实现条目是回归范围。
3. 代码：查 sdd_links.implements 找到实现这些条目的符号，再用任务文本和目标规格做一次代码混合检索；
   实现同组条目最多、检索也靠前的符号判为“需要修改”，实现约束条目的符号判为“相关（复用）”。
4. 测试：查 sdd_links.verifies。验证目标条目的测试是目标测试，其余验证所选条目的测试是相关回归测试。
5. 状态：从 PowerContext 读回已完成事项、待办和验证结果，并检查规格自上次记录后是否变化。
6. 核对：每个引用的来源都回到工程目录逐行比对，确认文件存在且内容与索引一致。
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .ingest import SPEC_ID
from .state import STEPS, TaskState, todo_for
from .store import Store

PLANNED_STATUSES = {"待实现", "变更中"}


@dataclass
class Task:
    id: str
    title: str
    description: str
    keep: list[str] = field(default_factory=list)
    source: str = ""

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.description}"

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "description": self.description, "keep": self.keep, "source": self.source}


def load_task(settings, ref: str) -> Task:
    """ref 可以是任务 ID（读取 samples/<ID>/task.toml）或 task.toml 的路径。"""
    path = Path(ref)
    if not path.suffix:
        path = settings.samples_dir / ref / "task.toml"
    elif not path.is_absolute():
        path = (settings.home / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"找不到任务定义：{path}（任务 ID 对应 samples/<ID>/task.toml）")
    data = tomllib.loads(path.read_text(encoding="utf-8"))["task"]
    return Task(
        id=data["id"],
        title=data["title"].strip(),
        description=data["description"].strip(),
        keep=[k.strip() for k in data.get("keep", [])],
        source=settings.rel(path),
    )


def _norm(values: dict[str, float]) -> dict[str, float]:
    top = max(values.values(), default=0.0)
    return {k: (v / top if top > 0 else 0.0) for k, v in values.items()}


class ContextBuilder:
    def __init__(self, store: Store, project: str, project_dir: Path) -> None:
        self.store = store
        self.project = project
        self.project_dir = project_dir

    # -------------------------------------------------------------- 规格

    def _select_specs(self, task: Task) -> dict:
        hits = self.store.hybrid_search(self.project, ["spec"], task.text, size=12, purpose="context: retrieve specs for task")
        keyword_scores = {h["chunk_id"]: h["_keyword_score"] for h in hits if h.get("_keyword_score")}
        kw_norm = _norm(keyword_scores)
        strong: list[dict] = []
        for rank, hit in enumerate(hits, 1):
            kw = kw_norm.get(hit["chunk_id"], 0.0)
            semantic_rank = hit.get("_semantic_rank")
            if kw >= 0.3 or (kw >= 0.15 and semantic_rank is not None and semantic_rank <= 3):
                strong.append({**hit, "rank": rank, "kw_norm": round(kw, 3)})
        strong = strong[:6]
        explicit = [f"spec:{s}" for s in dict.fromkeys(SPEC_ID.findall(task.text))]

        selected: dict[str, dict] = {}
        for hit in strong:
            reason = (
                f"任务检索命中：第 {hit['rank']} 名（全文第 {hit.get('_keyword_rank') or '-'} 名，"
                f"向量第 {hit.get('_semantic_rank') or '-'} 名，RRF {hit['_score']:.4f}）"
            )
            selected[hit["chunk_id"]] = {"role": "", "reasons": [reason], "search": hit}
        for chunk_id in explicit:
            selected.setdefault(chunk_id, {"role": "", "reasons": [], "search": None})["reasons"].append("任务文本直接引用")

        rows = self.store.chunks(self.project, list(selected), purpose="context: load matched specs")
        targets = [cid for cid in selected if rows.get(cid, {}).get("status") in PLANNED_STATUSES]
        if not targets and selected:
            # 没有待实现条目时，排在最前的命中就是要变更的条目
            targets = [next(cid for cid in selected if cid in rows)]
        for cid in selected:
            if cid in rows:
                selected[cid]["role"] = "target" if cid in targets else "constraint"

        # 目标条目引用的条目：必须遵守的约束
        for link in self.store.links(self.project, "references", sources=targets, purpose="context: specs referenced by targets"):
            cid = f"spec:{link['target']}"
            entry = selected.setdefault(cid, {"role": "constraint", "reasons": [], "search": None})
            entry["reasons"].append(f"被 {link['src_chunk'].split(':', 1)[1]} 引用")
            entry["role"] = entry["role"] or "constraint"

        # 与目标同一能力分组的已实现条目：回归范围
        groups = sorted({rows[cid]["grp"] for cid in targets if cid in rows})
        for row in self.store.specs_in_groups(self.project, groups, purpose="context: implemented specs in target groups"):
            cid = row["chunk_id"]
            if cid in selected or row["status"] in PLANNED_STATUSES:
                continue
            selected[cid] = {"role": "sibling", "reasons": [f"与目标同属分组「{row['grp']}」"], "search": None}

        all_rows = self.store.chunks(self.project, list(selected), purpose="context: load selected specs")
        result = {"target": [], "constraint": [], "sibling": []}
        for cid, info in selected.items():
            row = all_rows.get(cid)
            if row is None:
                continue
            result[info["role"]].append(self._spec_item(row, info))
        for items in result.values():
            items.sort(key=lambda item: item["id"])
        return {"specs": result, "hits": hits}

    @staticmethod
    def _spec_item(row: dict, info: dict) -> dict:
        return {
            "id": row["symbol"],
            "title": row["title"],
            "status": row["status"],
            "group": row["grp"],
            "path": row["path"],
            "start_line": row["start_line"],
            "end_line": row["end_line"],
            "revision": row["revision"],
            "content_sha": row["content_sha"],
            "content": row["content"],
            "reasons": info["reasons"],
        }

    # -------------------------------------------------------------- 代码

    def _select_code(self, task: Task, specs: dict) -> dict:
        all_specs = specs["target"] + specs["constraint"] + specs["sibling"]
        groups = {s["group"] for s in specs["target"]}
        group_specs = {s["id"] for s in all_specs if s["group"] in groups}  # 目标所在能力分组（同一接口）的全部条目
        other_specs = {s["id"] for s in all_specs} - group_specs
        implemented: dict[str, list[str]] = {}
        for link in self.store.links(
            self.project, "implements", targets=sorted(group_specs | other_specs), purpose="context: code implementing selected specs"
        ):
            implemented.setdefault(link["src_chunk"], []).append(link["target"])

        # 代码检索用任务标题和目标条目的分组、标题、接口、代码标识（反引号内容），比整段任务描述更贴近代码里的词
        query = "\n".join(
            [task.title] + [f"{s['group']} {s['title']} {_interface(s['content'])} {_backticks(s['content'])}" for s in specs["target"]]
        )
        hits = self.store.hybrid_search(self.project, ["code"], query, size=12, purpose="context: retrieve code for task")
        search = _norm({h["chunk_id"]: h["_score"] for h in hits})
        ranks = {h["chunk_id"]: rank for rank, h in enumerate(hits, 1)}

        group_count = {cid: len(group_specs.intersection(impl)) for cid, impl in implemented.items()}
        top = max(group_count.values(), default=0)
        scores = {
            cid: 2.0 * group_count.get(cid, 0) + 1.0 * len(other_specs.intersection(implemented.get(cid, []))) + 3.0 * search.get(cid, 0.0)
            for cid in set(implemented) | set(search)
        }
        rows = self.store.chunks(self.project, list(scores), purpose="context: load candidate code")
        to_change, related_impl, related_search = [], [], []
        for cid, score in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])):
            row = rows.get(cid)
            if row is None:
                continue
            impl = implemented.get(cid, [])
            reasons = []
            if impl:
                reasons.append("实现 " + ", ".join(sorted(impl)))
            if cid in ranks:
                reasons.append(f"代码检索第 {ranks[cid]} 名")
            item = {
                "chunk_id": cid,
                "path": row["path"],
                "symbol": row["symbol"],
                "signature": row["title"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "implements": sorted(impl),
                "score": round(score, 3),
                "reasons": reasons,
                "content": row["content"],
                "content_sha": row["content_sha"],
                "revision": row["revision"],
            }
            count = group_count.get(cid, 0)
            if count and count * 2 >= top:
                # 实现了该接口大部分现有条目的符号：新行为要加在这里
                item["reasons"].insert(0, f"实现同一接口的 {count} 个已有条目")
                to_change.append(item)
            elif impl:
                related_impl.append(item)
            elif search.get(cid, 0.0) >= 0.5:
                related_search.append(item)
        if not to_change:
            # 目标所在分组还没有任何实现：取检索最靠前的符号
            to_change = [item for item in related_search if search.get(item["chunk_id"], 0.0) >= 0.8][:2]
            related_search = [item for item in related_search if item not in to_change]
        related = related_impl + related_search[: max(0, 12 - len(related_impl))]
        return {"to_change": to_change, "related": related, "hits": hits}

    # -------------------------------------------------------------- 测试

    def _select_tests(self, specs: dict, code: dict) -> dict:
        targets = {s["id"] for s in specs["target"]}
        others = {s["id"] for s in specs["constraint"] + specs["sibling"]}
        for item in code["to_change"]:
            others.update(item["implements"])
        others -= targets
        verifies: dict[str, set[str]] = {}
        for link in self.store.links(
            self.project, "verifies", targets=sorted(targets | others), purpose="context: tests verifying selected specs"
        ):
            if link["kind"] == "test":
                verifies.setdefault(link["src_chunk"], set()).add(link["target"])
        rows = self.store.chunks(self.project, list(verifies), purpose="context: load selected tests")
        target, regression = [], []
        for cid in sorted(verifies, key=lambda c: (rows.get(c, {}).get("path", ""), rows.get(c, {}).get("start_line", 0))):
            row = rows.get(cid)
            if row is None:
                continue
            item = {
                "node_id": cid.split(":", 1)[1],
                "path": row["path"],
                "title": row["title"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "verifies": sorted(verifies[cid]),
                "content_sha": row["content_sha"],
                "revision": row["revision"],
                "content": row["content"],
            }
            if verifies[cid] & targets:
                target.append(item)
            else:
                regression.append(item)
        target_files = sorted({t["path"] for t in target})
        return {
            "target": target,
            "regression": regression,
            "commands": {
                "target": "python -m pytest -q " + " ".join(t["node_id"] for t in target),
                "regression": "python -m pytest -q " + " ".join(f"--deselect {t['node_id']}" for t in target),
                "related_regression": "python -m pytest -q " + " ".join(sorted({t["path"] for t in regression})),
            },
            "target_files": target_files,
        }

    # -------------------------------------------------------------- 状态

    @staticmethod
    def _state_section(state: TaskState | None, specs: dict, import_run: dict) -> dict:
        current = {s["id"]: s["content_sha"][:12] for role in ("target", "constraint") for s in specs[role]}
        if state is None:
            return {"available": False, "note": "未读取 PowerContext（--no-state）", "spec_revisions": current}
        latest = state.latest
        recorded = state.machine.get("spec_revisions", {})
        changed = sorted(k for k, v in current.items() if k in recorded and recorded[k] != v)
        added = sorted(set(current) - set(recorded)) if recorded else []
        extra = []
        if changed:
            extra.append(
                "规格 " + "、".join(changed) + " 在上次记录之后被修改并重新导入，之前的验证结果不再代表当前规格：需要按新规格重新验证（必要时重新修改代码）"
            )
        steps_done = [s for s in state.steps_done if not changed or s == "context"]
        todo = todo_for(steps_done, extra)
        next_step = next((s for s in STEPS if s not in steps_done), None)
        return {
            "available": True,
            "scope_title": state.scope_title,
            "scope_id": state.scope_id,
            "records": len(state.contracts) + len(state.outcomes),
            "empty": state.empty,
            "latest_status": latest.status if latest else None,
            "latest_summary": latest.summary if latest else None,
            "done": latest.observations if latest else [],
            "checks": latest.checks if latest else [],
            "todo": todo,
            "steps_done": steps_done,
            "next_step": next_step,
            "spec_changes": changed,
            "spec_added_since_record": added,
            "spec_revisions": current,
            "recorded_spec_revisions": recorded,
            "import_run": import_run["run_id"],
        }

    # -------------------------------------------------------------- 核对

    def _verify_sources(self, items: list[dict]) -> dict:
        cache: dict[str, list[str] | None] = {}
        problems = []
        for item in items:
            path = item["path"]
            if path not in cache:
                file = self.project_dir / path
                cache[path] = file.read_text(encoding="utf-8").splitlines() if file.is_file() else None
            lines = cache[path]
            if lines is None:
                item["source_check"] = "missing"
                problems.append(f"{path} 不存在")
                continue
            text = "\n".join(lines[item["start_line"] - 1 : item["end_line"]])
            if text == item["content"]:
                item["source_check"] = "ok"
            else:
                item["source_check"] = "changed"
                problems.append(f"{path}:{item['start_line']}-{item['end_line']} 与索引内容不一致（文件在导入后被修改，请重新导入）")
        return {"checked": len(items), "ok": len(items) - len(problems), "problems": problems}

    # -------------------------------------------------------------- 入口

    def build(self, task: Task, state: TaskState | None) -> dict:
        import_run = self.store.latest_import(self.project)
        if import_run is None:
            raise RuntimeError(f"seekdb 中还没有工程 {self.project} 的资料，请先执行 sddctx import")
        spec_part = self._select_specs(task)
        specs = spec_part["specs"]
        code = self._select_code(task, specs)
        tests = self._select_tests(specs, code)
        docs = self.store.q(
            "SELECT chunk_id, path, title, content, start_line, end_line, content_sha FROM sdd_chunks "
            "WHERE project = %s AND kind = 'doc' ORDER BY path, start_line",
            (self.project,),
            purpose="context: project conventions",
        )
        conventions = [
            {"path": d["path"], "title": d["title"], "start_line": d["start_line"], "end_line": d["end_line"], "content": d["content"]}
            for d in docs
        ]
        cited = [s for role in specs.values() for s in role] + code["to_change"] + code["related"]
        cited += tests["target"] + tests["regression"] + conventions
        verification = self._verify_sources(cited)
        for item in tests["regression"]:
            item.pop("content", None)  # 回归测试只输出位置，正文不放进上下文
        return {
            "task": task.to_dict(),
            "project": self.project,
            "import_run": {
                "run_id": import_run["run_id"],
                "tree_sha": import_run["tree_sha"],
                "code_version": import_run["code_version"],
                "finished_at": str(import_run["finished_at"]),
                "total": import_run["total"],
            },
            "specs": specs,
            "code": {"to_change": code["to_change"], "related": code["related"]},
            "tests": tests,
            "conventions": conventions,
            "state": self._state_section(state, specs, import_run),
            "retrieval": {
                "spec_hits": [_hit(h) for h in spec_part["hits"]],
                "code_hits": [_hit(h) for h in code["hits"]],
            },
            "source_verification": verification,
        }


def _interface(text: str) -> str:
    match = re.search(r"^-\s*接口\s*[：:]\s*(.+)$", text, re.M)
    return match.group(1).strip() if match else ""


def _backticks(text: str) -> str:
    return " ".join(re.findall(r"`([^`\n]{1,60})`", text))


def _hit(hit: dict) -> dict:
    return {
        "chunk_id": hit.get("chunk_id"),
        "score": round(hit.get("_score") or 0, 5),
        "keyword_rank": hit.get("_keyword_rank"),
        "keyword_score": round(hit["_keyword_score"], 3) if hit.get("_keyword_score") else None,
        "semantic_rank": hit.get("_semantic_rank"),
        "semantic_score": round(hit["_semantic_score"], 3) if hit.get("_semantic_score") else None,
    }
