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

"""Behavior tests for the batched HTTP Memory reranker."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory import MemoryEntryInput, MemoryHit
from powercontext.builtin.artifacts.memory.http_reranker import HTTPMemoryReranker
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts

_Handler = Callable[[httpx.Request], httpx.Response]


def _hit(rank: int) -> MemoryHit:
    return MemoryHit(
        memory_ref=ArtifactRef(family="memory", artifact_id="memory", revision=1),
        entry_id=f"entry-{rank}",
        entry_version_id=f"entry-{rank}-v1",
        text=f"Candidate {rank}",
        score=1 / rank,
        matched_by=("fts",),
    )


def _scoring(scores: dict[int, float], requests: list[dict[str, Any]] | None = None) -> _Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if requests is not None:
            requests.append(body)
        # Answer in reverse order: the response order carries no meaning.
        records = [{"rank": item["rank"], "score": scores[item["rank"]]} for item in reversed(body["candidates"])]
        return httpx.Response(200, json={"scores": records})

    return handler


def _rerank(handler: _Handler, candidates: tuple[MemoryHit, ...], limit: int, *, batch_size: int = 32):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            reranker = HTTPMemoryReranker("https://reranker.invalid/score", client=client, batch_size=batch_size)
            return await reranker.rerank("connection timeout", candidates, limit)

    return asyncio.run(scenario())


def test_selects_globally_across_batches_and_breaks_ties_by_original_rank() -> None:
    requests: list[dict[str, Any]] = []
    candidates = tuple(_hit(rank) for rank in range(1, 6))

    decision = _rerank(_scoring({1: 0.1, 2: 0.9, 3: 0.95, 4: 0.9, 5: -2.0}, requests), candidates, 3, batch_size=2)

    assert decision.selected_ranks == (3, 2, 4)
    assert decision.usage.requests == len(requests) == 3
    assert all(1 <= len(body["candidates"]) <= 2 and body["query"] == "connection timeout" for body in requests)
    sent = sorted((item["rank"], item["text"]) for body in requests for item in body["candidates"])
    assert sent == [(rank, f"Candidate {rank}") for rank in range(1, 6)]


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b'{"scores": [{"rank": 1, "score": 0.5}], "model": "x"}',
        b'{"scores": [{"rank": 1, "score": 0.5, "index": 0}]}',
        b'{"scores": [{"rank": 2, "score": 0.5}]}',
        b'{"scores": [{"rank": 1, "score": 0.5}, {"rank": 1, "score": 0.5}]}',
        b'{"scores": []}',
        b'{"scores": [{"rank": true, "score": 0.5}]}',
        b'{"scores": [{"rank": 1, "score": NaN}]}',
        b'{"scores": [{"rank": 1, "score": -Infinity}]}',
        b'{"scores": [{"rank": 1, "score": "0.5"}]}',
    ],
)
def test_rejects_responses_outside_the_score_schema(body: bytes) -> None:
    with pytest.raises(ValueError):
        _rerank(lambda _request: httpx.Response(200, content=body), (_hit(1),), 1)


def test_rejects_a_rank_from_another_batch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        ranks = [item["rank"] for item in json.loads(request.content)["candidates"]]
        answered = [3, 2] if ranks == [1, 2] else ranks
        return httpx.Response(200, json={"scores": [{"rank": rank, "score": 1.0} for rank in answered]})

    with pytest.raises(ValueError):
        _rerank(handler, tuple(_hit(rank) for rank in range(1, 4)), 1, batch_size=2)


def test_preserves_http_errors() -> None:
    def unavailable(request: httpx.Request) -> httpx.Response:
        ranks = [item["rank"] for item in json.loads(request.content)["candidates"]]
        if 3 in ranks:
            return httpx.Response(503, json={"error": "overloaded"})
        return httpx.Response(200, json={"scores": [{"rank": rank, "score": 1.0} for rank in ranks]})

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    candidates = tuple(_hit(rank) for rank in range(1, 5))
    with pytest.raises(httpx.HTTPStatusError) as raised:
        _rerank(unavailable, candidates, 1, batch_size=2)
    assert raised.value.response.status_code == 503
    with pytest.raises(httpx.ConnectError):
        _rerank(offline, candidates, 1, batch_size=2)


def test_validates_arguments() -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(_scoring({1: 1.0}))) as client:
            for batch_size in (0, -1):
                with pytest.raises(ValueError):
                    HTTPMemoryReranker("https://reranker.invalid", client=client, batch_size=batch_size)
            reranker = HTTPMemoryReranker("https://reranker.invalid", client=client)
            for candidates, limit in (((), 1), ((_hit(1),), 0), ((_hit(1),), 2)):
                with pytest.raises(ValueError):
                    await reranker.rerank("query", candidates, limit)

    asyncio.run(scenario())


def test_memory_search_selects_hits_by_service_scores() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            scores = [{"rank": item["rank"], "score": float("beta" in item["text"])} for item in body["candidates"]]
            return httpx.Response(200, json={"scores": scores})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            reranker = HTTPMemoryReranker("https://reranker.invalid/score", client=client, batch_size=1)
            async with open_builtin_contexts(
                BuiltinConfig(database=SQLiteConfig()), memory_reranker=reranker
            ) as contexts:
                memory = (await contexts.get("http-rerank")).artifacts.memory
                head = await memory.remember(
                    memory=None,
                    entries=(
                        MemoryEntryInput(kind="fact", text="Project alpha fact."),
                        MemoryEntryInput(kind="fact", text="Project beta fact."),
                        MemoryEntryInput(kind="fact", text="Project gamma fact."),
                    ),
                    mode="append",
                )
                assert head is not None
                result = await memory.search("project", memories=(head,), limit=1, mode="fts")

        assert result.rerank is not None
        assert result.rerank.policy_id == "http-cross-encoder-v1"
        assert result.rerank.usage.requests == len(result.rerank.candidate_hits) == 3
        assert [hit.text for hit in result.hits] == ["Project beta fact."]
        assert result.hits == tuple(result.rerank.candidate_hits[rank - 1] for rank in result.rerank.selected_ranks)

    asyncio.run(scenario())
