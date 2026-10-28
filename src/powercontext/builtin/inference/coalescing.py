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

"""Cross-call request coalescing and bounded vector caching for embedding models."""

from __future__ import annotations

import asyncio
import math
from collections import OrderedDict
from collections.abc import Iterable, Sequence
from typing import Literal

from powercontext.builtin.inference.errors import InvalidInferenceOutputError
from powercontext.builtin.inference.models import EmbeddingResult, EmbeddingVector, InferenceUsage
from powercontext.builtin.inference.protocols import EmbeddingModel, QueryEmbeddingModel

_InputType = Literal["document", "query"]
_Key = tuple[_InputType, str]
_Outcome = tuple[tuple[EmbeddingVector, ...], InferenceUsage]


class _Batch:
    """One provider request shared by every caller waiting on one of its texts."""

    __slots__ = ("future", "input_type", "loop", "positions", "timer")

    def __init__(self, input_type: _InputType, loop: asyncio.AbstractEventLoop) -> None:
        self.input_type = input_type
        self.loop = loop
        self.positions: dict[str, int] = {}
        self.future: asyncio.Future[_Outcome] = loop.create_future()
        self.timer: asyncio.Handle | None = None


class CoalescingEmbeddingModel:
    """Share in-flight embedding work across concurrent calls and cache successful vectors.

    Distinct texts requested within one coalescing window are sent together in provider
    requests of at most ``max_batch_size`` texts. A text that is already queued or being
    embedded joins that request instead of starting another one, and successful vectors
    stay in a least-recently-used cache of ``cache_size`` texts. Each call waits on the
    shared requests without owning them, so cancelling one caller never cancels work that
    other callers still await.
    """

    def __init__(
        self,
        model: EmbeddingModel,
        *,
        max_batch_size: int = 64,
        coalesce_ms: float = 5.0,
        cache_size: int = 1024,
    ) -> None:
        if isinstance(max_batch_size, bool) or not isinstance(max_batch_size, int) or max_batch_size < 1:
            raise ValueError("max_batch_size must be a positive integer")  # noqa: TRY003
        if (
            isinstance(coalesce_ms, bool)
            or not isinstance(coalesce_ms, (int, float))
            or not math.isfinite(coalesce_ms)
            or coalesce_ms < 0
        ):
            raise ValueError("coalesce_ms must be a finite non-negative number")  # noqa: TRY003
        if isinstance(cache_size, bool) or not isinstance(cache_size, int) or cache_size < 0:
            raise ValueError("cache_size must be a non-negative integer")  # noqa: TRY003
        self._model = model
        self.profile = model.profile
        self._max_batch_size = max_batch_size
        self._delay_seconds = coalesce_ms / 1000
        self._cache_size = cache_size
        self._cache: OrderedDict[_Key, EmbeddingVector] = OrderedDict()
        self._assigned: dict[_Key, _Batch] = {}
        self._open: dict[_InputType, _Batch] = {}
        self._running: set[asyncio.Task[None]] = set()

    async def embed(self, texts: Sequence[str], /) -> EmbeddingResult:
        """Return one vector per input position, sharing provider work with concurrent calls."""

        return await self._embed(tuple(texts), "document")

    async def embed_query(self, texts: Sequence[str], /) -> EmbeddingResult:
        """Embed retrieval queries, sharing document vectors when the provider is symmetric."""

        input_type: _InputType = "query" if isinstance(self._model, QueryEmbeddingModel) else "document"
        return await self._embed(tuple(texts), input_type)

    async def _embed(self, texts: tuple[str, ...], input_type: _InputType) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=())
        loop = asyncio.get_running_loop()
        resolved: dict[str, EmbeddingVector] = {}
        waiting: dict[str, tuple[_Batch, int]] = {}
        for text in dict.fromkeys(texts):
            key = (input_type, text)
            vector = self._cache.get(key)
            if vector is not None:
                self._cache.move_to_end(key)
                resolved[text] = vector
                continue
            batch = self._assigned.get(key)
            if batch is not None and batch.loop is loop:
                waiting[text] = (batch, batch.positions[text])
            else:
                waiting[text] = self._enqueue(key, loop)
        batches = list({id(batch): batch for batch, _ in waiting.values()}.values())
        if batches:
            # Waiting on the shared futures, rather than awaiting them directly, keeps a
            # cancelled caller from cancelling requests that other callers still need.
            await asyncio.wait([batch.future for batch in batches], return_when=asyncio.FIRST_EXCEPTION)
            for batch in batches:
                if batch.future.done() and (batch.future.cancelled() or batch.future.exception() is not None):
                    batch.future.result()
            for text, (batch, position) in waiting.items():
                resolved[text] = batch.future.result()[0][position]
        return EmbeddingResult(
            vectors=tuple(resolved[text] for text in texts),
            usage=_combined_usage(batch.future.result()[1] for batch in batches),
        )

    def _enqueue(self, key: _Key, loop: asyncio.AbstractEventLoop) -> tuple[_Batch, int]:
        input_type, text = key
        batch = self._open.get(input_type)
        if batch is None or batch.loop is not loop:
            batch = _Batch(input_type, loop)
            self._open[input_type] = batch
            batch.timer = (
                loop.call_later(self._delay_seconds, self._dispatch, batch)
                if self._delay_seconds > 0
                else loop.call_soon(self._dispatch, batch)
            )
        position = batch.positions[text] = len(batch.positions)
        self._assigned[key] = batch
        if len(batch.positions) >= self._max_batch_size:
            self._dispatch(batch)
        return batch, position

    def _dispatch(self, batch: _Batch) -> None:
        if self._open.get(batch.input_type) is not batch:
            return
        del self._open[batch.input_type]
        if batch.timer is not None:
            batch.timer.cancel()
            batch.timer = None
        task = batch.loop.create_task(self._run(batch))
        self._running.add(task)
        task.add_done_callback(self._running.discard)

    async def _run(self, batch: _Batch) -> None:
        texts = tuple(batch.positions)
        try:
            if batch.input_type == "query" and isinstance(self._model, QueryEmbeddingModel):
                result = await self._model.embed_query(texts)
            else:
                result = await self._model.embed(texts)
            vectors, usage = tuple(result.vectors), result.usage
        except asyncio.CancelledError:
            self._release(batch)
            batch.future.cancel()
            raise
        except Exception as error:
            self._fail(batch, error)
            return
        if len(vectors) != len(texts):
            self._fail(batch, InvalidInferenceOutputError("embed", "provider returned the wrong vector count"))
            return
        for text, vector in zip(texts, vectors, strict=True):
            self._remember((batch.input_type, text), vector)
        self._release(batch)
        batch.future.set_result((vectors, usage))

    def _fail(self, batch: _Batch, error: Exception) -> None:
        self._release(batch)
        batch.future.set_exception(error)
        # Every waiter re-raises the failure; a batch whose callers were all
        # cancelled must not report it as an unretrieved exception.
        batch.future.exception()

    def _release(self, batch: _Batch) -> None:
        for text in batch.positions:
            key = (batch.input_type, text)
            if self._assigned.get(key) is batch:
                del self._assigned[key]

    def _remember(self, key: _Key, vector: EmbeddingVector) -> None:
        if self._cache_size == 0:
            return
        self._cache[key] = vector
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)


def _combined_usage(usages: Iterable[InferenceUsage]) -> InferenceUsage:
    values = tuple(usages)
    return InferenceUsage(
        requests=sum(usage.requests for usage in values),
        input_tokens=_optional_sum(usage.input_tokens for usage in values),
        output_tokens=_optional_sum(usage.output_tokens for usage in values),
    )


def _optional_sum(values: Iterable[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


__all__ = ["CoalescingEmbeddingModel"]
