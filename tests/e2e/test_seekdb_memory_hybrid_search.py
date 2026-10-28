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

"""Memory hybrid search against a real embedded seekdb instance.

Embedded seekdb requires powercontext[seekdb]; without it these tests are skipped.
"""

from __future__ import annotations

import asyncio
import importlib.util
import math
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import Engine, event

from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput, MemorySearchResult
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts
from powercontext.builtin.tags import MemoryEntryTagTarget, TagFilter

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("pylibseekdb") is None,
    reason="install powercontext[seekdb] for the real embedded backend",
)

_PROFILE = EmbeddingProfile(profile_id="seekdb-hybrid-test-v1", model="table", dimension=4, distance="l2")


def _unit(*values: float) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in values))
    return tuple(value / norm for value in values)


class _TableEmbedding:
    """Embed known texts with fixed vectors and everything else as the query direction."""

    profile = _PROFILE

    def __init__(self, vectors: dict[str, tuple[float, ...]]) -> None:
        self._vectors = vectors

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(self._vectors.get(text, _unit(1, 0, 0, 0)) for text in texts))


@contextmanager
def _statements() -> Iterator[list[tuple[str, Any]]]:
    statements: list[tuple[str, Any]] = []

    def record(_connection, _cursor, statement, parameters, _context, _executemany) -> None:
        statements.append((statement, parameters))

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(Engine, "before_cursor_execute", record)


def test_hybrid_search_reads_both_native_channels_in_one_statement(tmp_path) -> None:
    embedding = _TableEmbedding({
        "Alpha semantic record.": _unit(1, 0, 0, 0),
        "Beta lexical record.": _unit(0, 1, 0, 0),
        "Gamma appended record.": _unit(0, 0, 1, 0),
        "Alpha decoy in another scope.": _unit(1, 0, 0, 0),
    })

    async def scenario() -> None:
        config = BuiltinConfig(database=SeekDBConfig(path=tmp_path / "seekdb"))
        async with open_builtin_contexts(config, embedding_model=embedding) as contexts:
            memory = (await contexts.get("project")).artifacts.memory
            first = await memory.remember(
                memory=None,
                entries=(
                    MemoryEntryInput(kind="fact", text="Alpha semantic record."),
                    MemoryEntryInput(kind="fact", text="Beta lexical record."),
                ),
                mode="append",
            )
            assert first is not None
            # Unchanged entries keep the projection rows written for the first revision.
            head = await memory.remember(
                memory=first,
                entries=(MemoryEntryInput(kind="fact", text="Gamma appended record."),),
                mode="append",
            )
            assert head is not None
            other = (await contexts.get("other")).artifacts.memory
            await other.remember(
                memory=None,
                entries=(MemoryEntryInput(kind="fact", text="Alpha decoy in another scope."),),
                mode="append",
            )

            with _statements() as statements:
                alpha = await memory.search("alpha", memories=(head,), mode="hybrid", limit=10)
            candidates = [
                (statement, parameters)
                for statement, parameters in statements
                if "AGAINST" in statement.upper() or "l2_distance" in statement.lower()
            ]
            # The query vector stays on the alpha direction, so each channel finds a different entry.
            gamma = await memory.search("gamma", memories=(head,), mode="hybrid", limit=10)

            async with contexts.database.transaction() as connection:
                [(statement, parameters)] = candidates
                plan = "\n".join(
                    str(row[0]) for row in (await connection.exec_driver_sql(f"EXPLAIN {statement}", parameters)).all()
                )

        assert "AGAINST" in statement.upper() and "l2_distance" in statement.lower()
        assert "TEXT RETRIEVAL SCAN" in plan
        assert "VECTOR INDEX" in plan
        assert [(hit.text, hit.matched_by) for hit in alpha.hits] == [("Alpha semantic record.", ("fts", "vector"))]
        assert sorted((hit.text, hit.matched_by) for hit in gamma.hits) == [
            ("Alpha semantic record.", ("vector",)),
            ("Gamma appended record.", ("fts",)),
        ]
        assert all(hit.memory_ref == head.as_ref() for hit in (*alpha.hits, *gamma.hits))

    asyncio.run(scenario())


def test_tagged_hybrid_search_ranks_every_tagged_entry_of_a_large_memory(tmp_path) -> None:
    # Hundreds of entries lie closer to the query than the tagged ones, so a nearest-
    # neighbour cut taken before the tag filter would leave no tagged vector candidate.
    near = {f"Near note {index}.": _unit(1, 0.01 * (index % 7), 0.01 * (index % 5), 0) for index in range(240)}
    tagged = {f"Tagged note {index}.": _unit(0.7, 0.7, 0.1 * index, 0) for index in range(6)}
    embedding = _TableEmbedding(near | tagged)

    async def scenario() -> MemorySearchResult:
        config = BuiltinConfig(database=SeekDBConfig(path=tmp_path / "seekdb"))
        async with open_builtin_contexts(config, embedding_model=embedding) as contexts:
            memory = (await contexts.get("project")).artifacts.memory
            head = await memory.remember(
                memory=None,
                entries=tuple(MemoryEntryInput(kind="fact", text=text) for text in (*near, *tagged)),
                mode="append",
            )
            assert head is not None
            for entry in await memory.entries(head):
                if entry.text in tagged:
                    target = MemoryEntryTagTarget(artifact_id=head.artifact_id, entry_id=entry.entry_id)
                    empty = await contexts.records.get_tags("project", target)
                    await contexts.records.replace_tags("project", target, ("selected",), expected_etag=empty.etag)
            return await memory.search(
                "zebra", memories=(head,), mode="hybrid", limit=10, tag_filter=TagFilter(tags=("selected",))
            )

    result = asyncio.run(scenario())

    assert [hit.text for hit in result.hits] == list(tagged)
    assert all(hit.matched_by == ("vector",) for hit in result.hits)
