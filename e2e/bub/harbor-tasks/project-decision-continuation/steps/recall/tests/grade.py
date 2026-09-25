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

"""Grade the recall answer without depending on the agent host.

This file is uploaded only with the recall step's tests, so no earlier session can read the expected answer.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

# Every group must match; any alternative inside a group is enough.
REQUIRED = (("oceanbase",), ("12", "twelve"))


def score(answer: str) -> int:
    text = unicodedata.normalize("NFC", answer.casefold())
    return int(
        all(any(re.search(rf"\b{re.escape(term)}\b", text) for term in group) for group in REQUIRED),
    )


def main(answer_path: Path, reward_path: Path) -> None:
    answer = answer_path.read_text(encoding="utf-8", errors="replace") if answer_path.is_file() else ""
    reward_path.write_text(f"{score(answer)}\n", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
