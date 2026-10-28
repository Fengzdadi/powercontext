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

"""Batched HTTP scoring for coarse Memory search candidates."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Iterable, Mapping
from typing import Any, TypeVar

import httpx

from powercontext.builtin.artifacts.memory.models import MemoryHit
from powercontext.builtin.artifacts.memory.reranking import MemoryRerankDecision, _validate_bounds
from powercontext.builtin.inference import InferenceUsage

HTTP_RERANK_POLICY_ID = "http-cross-encoder-v1"

_Score = int | float
_T = TypeVar("_T")


class _InvalidRerankResponseError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        messages = {
            "json": "rerank service response is not valid JSON",
            "body": "rerank service response must be an object containing exactly 'scores'",
            "scores": "rerank service 'scores' must be a list",
            "record": "rerank score records must contain exactly 'rank' and 'score'",
            "rank": "rerank score rank must be an integer from the request batch",
            "duplicate": "rerank score rank is repeated",
            "coverage": "rerank scores must cover every rank in the request batch",
            "score": "rerank score must be a finite number",
        }
        super().__init__(messages[code])


class HTTPMemoryReranker:
    """Select Memory hits by scores from an HTTP scoring service.

    The service scores at most ``batch_size`` candidates per request, so the pool is sent in
    batches that keep each candidate's one-based rank in the complete pool. Every response
    must score exactly the ranks of its own request. The selection then orders the whole pool
    by descending score and ascending original rank, so neither batch boundaries nor the order
    in which batches complete affect the result. Batches are sent concurrently; the caller's
    ``httpx.AsyncClient`` connection limits bound how many are in flight.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient,
        batch_size: int = 32,
        policy_id: str = HTTP_RERANK_POLICY_ID,
    ) -> None:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("rerank batch size must be a positive integer")  # noqa: TRY003
        if not policy_id:
            raise ValueError("rerank policy ID must not be empty")  # noqa: TRY003
        self.policy_id = policy_id
        self._endpoint = endpoint
        self._client = client
        self._batch_size = batch_size

    async def rerank(
        self,
        query: str,
        candidates: tuple[MemoryHit, ...],
        limit: int,
        /,
    ) -> MemoryRerankDecision:
        """Score every candidate and return the globally best original ranks."""

        _validate_bounds(len(candidates), limit)
        batches = tuple(
            range(start, min(start + self._batch_size, len(candidates) + 1))
            for start in range(1, len(candidates) + 1, self._batch_size)
        )
        scores: dict[int, _Score] = {}
        for batch_scores in await _all_or_cancel(self._score(query, candidates, batch) for batch in batches):
            scores.update(batch_scores)
        selected = sorted(scores, key=lambda rank: (-scores[rank], rank))[:limit]
        return MemoryRerankDecision(
            selected_ranks=tuple(selected),
            usage=InferenceUsage(requests=len(batches)),
        )

    async def _score(self, query: str, candidates: tuple[MemoryHit, ...], ranks: range) -> dict[int, _Score]:
        response = await self._client.post(
            self._endpoint,
            json={
                "query": query,
                "candidates": [{"rank": rank, "text": candidates[rank - 1].text} for rank in ranks],
            },
        )
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError as error:
            raise _InvalidRerankResponseError("json") from error
        return _batch_scores(body, ranks)


def _batch_scores(body: Any, ranks: range) -> dict[int, _Score]:
    if not isinstance(body, Mapping) or set(body) != {"scores"}:
        raise _InvalidRerankResponseError("body")
    records = body["scores"]
    if not isinstance(records, list):
        raise _InvalidRerankResponseError("scores")
    scores: dict[int, _Score] = {}
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {"rank", "score"}:
            raise _InvalidRerankResponseError("record")
        rank = record["rank"]
        score = record["score"]
        # JSON booleans decode to Python bools, which are ints; neither is a rank or score.
        if isinstance(rank, bool) or not isinstance(rank, int) or rank not in ranks:
            raise _InvalidRerankResponseError("rank")
        if rank in scores:
            raise _InvalidRerankResponseError("duplicate")
        if isinstance(score, bool) or not isinstance(score, int | float) or not _finite(score):
            raise _InvalidRerankResponseError("score")
        scores[rank] = score
    if len(scores) != len(ranks):
        raise _InvalidRerankResponseError("coverage")
    return scores


def _finite(score: _Score) -> bool:
    # Python ints are exact and unbounded; only floats can be NaN or infinite.
    return isinstance(score, int) or math.isfinite(score)


async def _all_or_cancel(requests: Iterable[Awaitable[_T]]) -> list[_T]:
    """Await every request, cancelling the rest and re-raising the first failure unchanged."""

    tasks = [asyncio.ensure_future(request) for request in requests]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


__all__ = ["HTTP_RERANK_POLICY_ID", "HTTPMemoryReranker"]
