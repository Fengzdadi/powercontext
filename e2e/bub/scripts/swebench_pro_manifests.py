# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Write paired workload manifests for a subset of Harbor's SWE-bench Pro dataset.

Download the dataset first, so each manifest pins the task's checksum::

    uv run --project e2e/bub harbor datasets download swebenchpro@1.0 -o <dir>
    uv run --project e2e/bub python e2e/bub/scripts/swebench_pro_manifests.py <dir>/swebenchpro

The subset is the first ``--per-repository`` tasks of every repository, by task name, so the same dataset always
gives the same manifests. Pass ``--task`` to select tasks by name instead.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

from harbor.models.task.task import Task

DATASET = "swebenchpro"
VERSION = "1.0"
HEADER = """\
# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
# instance_<owner>__<repository>-<commit>[-v<commit or nan>]; a repository name may contain hyphens.
TASK_NAME = re.compile(
    r"^instance_(?P<owner>.+?)__(?P<repository>.+)-(?P<commit>[0-9a-f]{40})(-v(?:[0-9a-f]{40}|nan))?$"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset_dir", type=Path, help="The downloaded swebenchpro dataset directory.")
    parser.add_argument("--output", type=Path, default=Path("e2e/bub/paired-tasks/swebench-pro"))
    parser.add_argument("--per-repository", type=int, default=1)
    parser.add_argument("--task", action="append", default=[], help="Select a task by name instead of the rule.")
    args = parser.parse_args()

    tasks = sorted(path for path in args.dataset_dir.iterdir() if path.is_dir())
    if args.task:
        by_name = {path.name: path for path in tasks}
        if unknown := sorted(set(args.task) - set(by_name)):
            raise SystemExit(f"Tasks not in {args.dataset_dir}: {unknown!r}")  # noqa: TRY003
        selected = [by_name[name] for name in sorted(set(args.task))]
    else:
        by_repository: dict[str, list[Path]] = defaultdict(list)
        for path in tasks:
            by_repository[_repository(path.name)].append(path)
        selected = [path for paths in by_repository.values() for path in paths[: args.per_repository]]
    args.output.mkdir(parents=True, exist_ok=True)
    for path in selected:
        manifest = args.output / f"{_workload_id(path.name)}.yaml"
        manifest.write_text(HEADER + _manifest(path), encoding="utf-8")
        print(manifest)


def _repository(task_name: str) -> str:
    match = TASK_NAME.match(task_name)
    if match is None:
        raise ValueError(f"Unexpected SWE-bench Pro task name {task_name!r}")  # noqa: TRY003
    return match["repository"]


def _workload_id(task_name: str) -> str:
    match = TASK_NAME.match(task_name)
    if match is None:
        raise ValueError(f"Unexpected SWE-bench Pro task name {task_name!r}")  # noqa: TRY003
    return f"swebench-pro-{match['repository']}-{match['commit'][:8]}"


def _manifest(path: Path) -> str:
    task = Task(path)
    repository = _repository(path.name)
    return f"""
schema: powercontext.e2e-task/v1
id: {_workload_id(path.name)}
categories:
  - paired
  - swebench-pro
  - swebench-pro-{repository}
dataset:
  name: {DATASET}
  version: "{VERSION}"
  task_id: "{path.name}"
  checksum: "{task.checksum}"
execution:
  type: bub
  model: true
  max_steps: 200
  max_tokens: 16384
evaluation:
  comparison: task-outcome
"""


if __name__ == "__main__":
    main()
