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

"""Propagate Source withdrawal and restoration through registered evidence dependencies.

Each scope holds a DAG of Source, Memory entry, and Topic Memory nodes. A derived
node is available when all (``"all"``) or any (``"any"``) of its parents are. The
event log is authoritative and node availability is derived from it. Memory
nodes project their availability onto the native entry state, so Memory list,
search, and Context follow it; withdrawn Topic revisions leave native Topic
search. Registered references stay exactly readable for audit either way.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncConnection

from powercontext.artifacts import ArtifactRef, MemoryCitation
from powercontext.builtin.artifacts.topic_memory import TopicMemory
from powercontext.builtin.persistence.source_lifecycle import (
    LifecycleEventRecord,
    LifecycleNode,
    LifecyclePolicy,
    LifecycleReference,
    SourceLifecycleRepository,
)
from powercontext.builtin.persistence.tables import MAX_SOURCE_LIFECYCLE_NODE_ID_LENGTH
from powercontext.builtin.records import BaseAccessError
from powercontext.builtin.sources import validate_scope_id
from powercontext.errors import RevisionConflictError
from powercontext.sources import SourceRef

if TYPE_CHECKING:
    from powercontext.builtin.context import BuiltinArtifacts, BuiltinSources
    from powercontext.builtin.persistence.database import AsyncDatabase
    from powercontext.builtin.runtime.application import BuiltinRuntime
    from powercontext.builtin.runtime.protocols import BuiltinTriggers
    from powercontext.context import PowerContext

SourceLifecyclePurpose = Literal["generation", "audit"]

# Stored identities and counters are signed 64-bit integers on every backend.
_MAX_STORED_INTEGER = 2**63 - 1
_NATIVE_WRITE_ATTEMPTS = 3
_WITHDRAWN_REASON = "source-lifecycle-withdrawn"
_RESTORED_REASON = "source-lifecycle-restored"


class SourceLifecycleError(ValueError):
    """A lifecycle registration, event, or resolution violates its contract."""

    def __init__(self, code: str, node_id: str | None = None) -> None:
        self.code = code
        self.node_id = node_id
        super().__init__(code if node_id is None else f"{code}: {node_id!r}")


class SourceLifecycleEvent(BaseModel):
    """One ordered availability change for a registered Source."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    node_id: str
    revision: int = Field(ge=1)
    sequence: int = Field(ge=1)
    available: bool
    reason: str

    @field_validator("node_id", "reason")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")  # noqa: TRY003
        return value


class _LifecycleUnavailableError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Source lifecycle storage is not configured")


class SourceLifecycleApplication:
    """Select the lifecycle service for one scope."""

    def __init__(self, runtime: BuiltinRuntime, database: AsyncDatabase | None) -> None:
        self._runtime = runtime
        self._database = database

    def for_scope(self, scope_id: str, /) -> ScopedSourceLifecycleApplication:
        return ScopedSourceLifecycleApplication(self._runtime, self._database, scope_id)


class ScopedSourceLifecycleApplication:
    """Register evidence dependencies in one scope and propagate Source availability.

    A scope has a single writer and registrations never change, so registration
    order is a topological order and every derived node is computed from parents
    that already exist.
    """

    def __init__(self, runtime: BuiltinRuntime, database: AsyncDatabase | None, scope_id: str) -> None:
        self._runtime = runtime
        self._database = database
        self.scope_id = validate_scope_id(scope_id)
        self._nodes = SourceLifecycleRepository()

    async def register_source(self, node_id: str, source_ref: SourceRef, revision: int = 1) -> None:
        """Register a captured Source; it is available until an event withdraws it."""

        node_id = _node_id(node_id)
        if not isinstance(source_ref, SourceRef):
            raise SourceLifecycleError("invalid-reference", node_id)
        if type(revision) is not int or not 1 <= revision <= _MAX_STORED_INTEGER:
            raise SourceLifecycleError("invalid-revision", node_id)
        await self._register(
            LifecycleNode(
                node_id=node_id,
                kind="source",
                reference=SourceRef.model_validate(source_ref.model_dump()),
                lifecycle_revision=revision,
            )
        )

    async def register_memory(
        self,
        node_id: str,
        citation: MemoryCitation,
        parents: tuple[str, ...],
        policy: LifecyclePolicy = "all",
    ) -> None:
        """Bind one readable Memory entry version to the parents that support it."""

        node_id = _node_id(node_id)
        if not isinstance(citation, MemoryCitation):
            raise SourceLifecycleError("invalid-reference", node_id)
        await self._register(
            LifecycleNode(
                node_id=node_id,
                kind="memory",
                reference=MemoryCitation.model_validate(citation.model_dump()),
                parents=_parents(node_id, parents),
                policy=_policy(node_id, policy),
            )
        )

    async def register_topic(
        self,
        node_id: str,
        artifact_ref: ArtifactRef,
        parents: tuple[str, ...],
        policy: LifecyclePolicy = "all",
    ) -> None:
        """Bind one readable Topic Memory revision to the parents that support it."""

        node_id = _node_id(node_id)
        if not isinstance(artifact_ref, ArtifactRef) or artifact_ref.family != TopicMemory.family:
            raise SourceLifecycleError("invalid-reference", node_id)
        await self._register(
            LifecycleNode(
                node_id=node_id,
                kind="topic",
                reference=ArtifactRef.model_validate(artifact_ref.model_dump()),
                parents=_parents(node_id, parents),
                policy=_policy(node_id, policy),
            )
        )

    async def apply(self, event: SourceLifecycleEvent, /) -> list[str]:
        """Record one Source event, propagate it, and return every available node id in order.

        Replaying the newest event of a Source changes nothing; it only finishes
        native Memory writes that an earlier attempt left incomplete.
        """

        event = SourceLifecycleEvent.model_validate(event)
        if event.sequence > _MAX_STORED_INTEGER or event.revision > _MAX_STORED_INTEGER:
            raise SourceLifecycleError("invalid-event", event.node_id)
        record = LifecycleEventRecord(
            sequence=event.sequence,
            revision=event.revision,
            available=event.available,
            reason=event.reason,
        )
        database = self._require_database()
        async with self._runtime._context(self.scope_id) as context, self._runtime._locked(self.scope_id):
            async with database.transaction() as connection:
                source = await self._nodes.node(connection, self.scope_id, event.node_id, for_update=True)
                if source is None or source.kind != "source":
                    raise SourceLifecycleError("unknown-source", event.node_id)
                if event.revision != source.lifecycle_revision:
                    raise SourceLifecycleError("revision-mismatch", event.node_id)
                last = await self._nodes.last_event(connection, self.scope_id, event.node_id)
                if last is not None and record.sequence <= last.sequence:
                    if record != last:
                        code = "stale-sequence" if record.sequence < last.sequence else "conflicting-event"
                        raise SourceLifecycleError(code, event.node_id)
                else:
                    await self._nodes.add_event(connection, self.scope_id, event.node_id, record)
                    await self._propagate(connection, {event.node_id: event.available})
            await self._synchronize_memory(context)
            async with database.transaction() as connection:
                nodes = await self._nodes.scope_nodes(connection, self.scope_id)
        return sorted(node.node_id for node in nodes if node.available)

    async def resolve(self, node_id: str, purpose: SourceLifecyclePurpose = "generation") -> LifecycleReference:
        """Return a node's registered reference, refusing unavailable nodes for generation."""

        if purpose not in ("generation", "audit"):
            raise SourceLifecycleError("unknown-purpose")
        if not isinstance(node_id, str):
            raise SourceLifecycleError("unknown-node")
        database = self._require_database()
        async with self._runtime._scope_operation(self.scope_id), database.transaction() as connection:
            node = await self._nodes.node(connection, self.scope_id, node_id)
        if node is None:
            raise SourceLifecycleError("unknown-node", node_id)
        if purpose == "generation" and not node.available:
            raise SourceLifecycleError("unavailable", node_id)
        return node.reference

    async def _register(self, node: LifecycleNode) -> None:
        database = self._require_database()
        async with self._runtime._context(self.scope_id) as context, self._runtime._locked(self.scope_id):
            async with database.transaction() as connection:
                existing = await self._nodes.node(connection, self.scope_id, node.node_id)
                parents = await self._nodes.nodes(connection, self.scope_id, node.parents)
            if existing is not None:
                if _binding(existing) != _binding(node):
                    raise SourceLifecycleError("conflicting-registration", node.node_id)
            else:
                if len(parents) != len(node.parents):
                    raise SourceLifecycleError("unknown-parent", node.node_id)
                await self._require_readable(node, context)
                async with database.transaction() as connection:
                    parents = await self._nodes.nodes(connection, self.scope_id, node.parents)
                    if len(parents) != len(node.parents):
                        raise SourceLifecycleError("unknown-parent", node.node_id)
                    available = node.kind == "source" or _supported(
                        node, {parent_id: parent.available for parent_id, parent in parents.items()}
                    )
                    # A derived node starts from its parents' current state; an unsupported
                    # Memory entry must leave native recall before this call returns.
                    await self._nodes.add(
                        connection,
                        self.scope_id,
                        replace(node, available=available, native_pending=node.kind == "memory" and not available),
                    )
            await self._synchronize_memory(context)

    async def _require_readable(
        self,
        node: LifecycleNode,
        context: PowerContext[BuiltinSources, BuiltinArtifacts, BuiltinTriggers],
    ) -> None:
        """Read the registered reference exactly as callers will later resolve it."""

        reference = node.reference
        readable = True
        try:
            if isinstance(reference, SourceRef):
                await self._runtime._records().get_source(self.scope_id, reference.source_type, reference.source_id)
            elif isinstance(reference, MemoryCitation):
                service = context.artifacts.memory
                memory = await service.revision(reference.memory_ref)
                readable = memory.artifact_id == context.artifacts.memory_artifact_id and any(
                    item.entry_id == reference.entry_id and item.entry_version_id == reference.entry_version_id
                    for item in memory.content.manifest.entries
                )
                if readable:
                    await service.validate_citation(reference)
            elif self._runtime._topic_memory_get is None:
                readable = False
            else:
                await self._runtime._topic_memory_get(self.scope_id, reference)
        except (BaseAccessError, LookupError, ValueError) as error:
            raise SourceLifecycleError("unreadable-reference", node.node_id) from error
        if not readable:
            raise SourceLifecycleError("unreadable-reference", node.node_id)

    async def _propagate(self, connection: AsyncConnection, sources: Mapping[str, bool]) -> None:
        available: dict[str, bool] = {}
        for node in await self._nodes.scope_nodes(connection, self.scope_id):
            value = sources.get(node.node_id, node.available) if node.kind == "source" else _supported(node, available)
            available[node.node_id] = value
            if value != node.available:
                await self._nodes.set_available(connection, self.scope_id, node, value)

    async def _synchronize_memory(
        self,
        context: PowerContext[BuiltinSources, BuiltinArtifacts, BuiltinTriggers],
    ) -> None:
        """Project lifecycle availability onto native Memory entry state, one entry at a time.

        An entry stays pending until its native state matches, so an interrupted
        propagation resumes on the next call and a settled entry is never written again.
        """

        database = self._require_database()
        async with database.transaction() as connection:
            pending = await self._nodes.pending_memory_entries(connection, self.scope_id)
        service = context.artifacts.memory
        for entry_id in pending:
            async with database.transaction() as connection:
                available = await self._nodes.entry_availability(connection, self.scope_id, entry_id)
            target = "active" if available else "inactive"
            for attempt in range(1, _NATIVE_WRITE_ATTEMPTS + 1):
                memory, versions = await service.head_entries(context.artifacts.memory_artifact_id)
                state = next(
                    (item.state for item in memory.content.manifest.entries if item.entry_id == entry_id), None
                )
                version = next((item for item in versions if item.entry_id == entry_id), None)
                if version is None or state is None or state == target:
                    break
                try:
                    if available:
                        await service.reactivate(memory, entries=(version,), reason=_RESTORED_REASON)
                    else:
                        await service.forget(memory, entries=(version,), reason=_WITHDRAWN_REASON)
                except RevisionConflictError:
                    # Another writer moved the Memory head; re-read it and retry the transition.
                    if attempt == _NATIVE_WRITE_ATTEMPTS:
                        raise
                    continue
                break
            async with database.transaction() as connection:
                await self._nodes.settle_entry(connection, self.scope_id, entry_id)

    def _require_database(self) -> AsyncDatabase:
        if self._database is None:
            raise _LifecycleUnavailableError
        return self._database


def _node_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_SOURCE_LIFECYCLE_NODE_ID_LENGTH:
        raise SourceLifecycleError("invalid-node-id")
    return value


def _parents(node_id: str, value: object) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Iterable):
        raise SourceLifecycleError("invalid-parents", node_id)
    parents = tuple(value)
    if not parents:
        raise SourceLifecycleError("missing-parents", node_id)
    if not all(isinstance(parent, str) and parent.strip() for parent in parents):
        raise SourceLifecycleError("invalid-parents", node_id)
    if len(set(parents)) != len(parents):
        raise SourceLifecycleError("duplicate-parent", node_id)
    if node_id in parents:
        raise SourceLifecycleError("cyclic-dependency", node_id)
    # Support depends on the set of parents, so their order is not part of the binding.
    return tuple(sorted(parents))


def _policy(node_id: str, value: object) -> LifecyclePolicy:
    if value == "all":
        return "all"
    if value == "any":
        return "any"
    raise SourceLifecycleError("invalid-policy", node_id)


def _supported(node: LifecycleNode, available: Mapping[str, bool]) -> bool:
    support = [available.get(parent, False) for parent in node.parents]
    return all(support) if node.policy == "all" else any(support)


def _binding(node: LifecycleNode) -> tuple[object, ...]:
    return (node.kind, node.reference, node.parents, node.policy, node.lifecycle_revision)


__all__ = [
    "ScopedSourceLifecycleApplication",
    "SourceLifecycleApplication",
    "SourceLifecycleError",
    "SourceLifecycleEvent",
    "SourceLifecyclePurpose",
]
