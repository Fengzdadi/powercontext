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

"""Persisted Source lifecycle registrations, events, and derived availability."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, cast

import rfc8785
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from powercontext.artifacts import ArtifactRef, MemoryCitation
from powercontext.builtin.artifacts.topic_memory import TopicMemoryChannelHit, TopicMemorySearchChannels
from powercontext.builtin.persistence.codec import dump_model, load_model, stored_bytes
from powercontext.builtin.persistence.errors import InvalidStoredPayloadError
from powercontext.builtin.persistence.tables import SOURCE_LIFECYCLE_EVENTS_TABLE, SOURCE_LIFECYCLE_NODES_TABLE
from powercontext.sources import SourceRef

LifecycleNodeKind = Literal["source", "memory", "topic"]
LifecyclePolicy = Literal["all", "any"]
LifecycleReference = SourceRef | MemoryCitation | ArtifactRef

_REFERENCE_MODELS: dict[str, type[SourceRef] | type[MemoryCitation] | type[ArtifactRef]] = {
    "source": SourceRef,
    "memory": MemoryCitation,
    "topic": ArtifactRef,
}
_PARENTS = TypeAdapter(tuple[str, ...])
# Every ranked channel, so a channel added to the search model is filtered as well.
_TOPIC_CHANNELS = tuple(
    name
    for name, field in TopicMemorySearchChannels.model_fields.items()
    if field.annotation == tuple[TopicMemoryChannelHit, ...]
)


@dataclass(frozen=True)
class LifecycleNode:
    """One registered evidence node and its current derived availability."""

    node_id: str
    kind: LifecycleNodeKind
    reference: LifecycleReference
    parents: tuple[str, ...] = ()
    policy: LifecyclePolicy | None = None
    lifecycle_revision: int | None = None
    available: bool = True
    native_pending: bool = False

    @property
    def target_id(self) -> str | None:
        """Return the native identity this node governs: a Memory entry or a Topic artifact."""

        if isinstance(self.reference, MemoryCitation):
            return self.reference.entry_id
        if isinstance(self.reference, ArtifactRef):
            return self.reference.artifact_id
        return None


@dataclass(frozen=True)
class LifecycleEventRecord:
    """The persisted identity of one applied Source lifecycle event."""

    sequence: int
    revision: int
    available: bool
    reason: str


class SourceLifecycleRepository:
    """Read and write lifecycle rows inside a transaction owned by the caller."""

    async def node(
        self,
        connection: AsyncConnection,
        scope_id: str,
        node_id: str,
        /,
        *,
        for_update: bool = False,
    ) -> LifecycleNode | None:
        table = SOURCE_LIFECYCLE_NODES_TABLE
        condition = (table.c.scope_id == scope_id) & (table.c.node_id == node_id)
        if for_update and connection.dialect.name == "sqlite":
            # SQLite ignores FOR UPDATE; a matching no-op UPDATE opens the write transaction first.
            await connection.execute(update(table).where(condition).values(ordinal=table.c.ordinal))
        statement = select(table).where(condition)
        if for_update:
            statement = statement.with_for_update()
        row = (await connection.execute(statement)).mappings().one_or_none()
        return None if row is None else _node(row)

    async def nodes(
        self, connection: AsyncConnection, scope_id: str, node_ids: Iterable[str], /
    ) -> dict[str, LifecycleNode]:
        table = SOURCE_LIFECYCLE_NODES_TABLE
        selected = sorted(set(node_ids))
        if not selected:
            return {}
        rows = (
            await connection.execute(select(table).where(table.c.scope_id == scope_id, table.c.node_id.in_(selected)))
        ).mappings()
        return {node.node_id: node for node in map(_node, rows)}

    async def scope_nodes(self, connection: AsyncConnection, scope_id: str, /) -> tuple[LifecycleNode, ...]:
        """Return every node of one scope in registration, and therefore topological, order."""

        table = SOURCE_LIFECYCLE_NODES_TABLE
        rows = (
            await connection.execute(select(table).where(table.c.scope_id == scope_id).order_by(table.c.ordinal))
        ).mappings()
        return tuple(map(_node, rows))

    async def add(self, connection: AsyncConnection, scope_id: str, node: LifecycleNode, /) -> None:
        table = SOURCE_LIFECYCLE_NODES_TABLE
        ordinal = await connection.scalar(select(func.max(table.c.ordinal)).where(table.c.scope_id == scope_id))
        await connection.execute(
            insert(table).values(
                scope_id=scope_id,
                node_id=node.node_id,
                ordinal=int(ordinal or 0) + 1,
                kind=node.kind,
                reference=dump_model(node.reference, kind="source-lifecycle", name=node.node_id),
                target_id=node.target_id,
                target_revision=node.reference.revision if isinstance(node.reference, ArtifactRef) else None,
                lifecycle_revision=node.lifecycle_revision,
                policy=node.policy,
                parents=rfc8785.dumps(list(node.parents)),
                available=node.available,
                native_pending=node.native_pending,
            )
        )

    async def last_event(
        self,
        connection: AsyncConnection,
        scope_id: str,
        node_id: str,
        /,
    ) -> LifecycleEventRecord | None:
        table = SOURCE_LIFECYCLE_EVENTS_TABLE
        row = (
            (
                await connection.execute(
                    select(table.c.sequence, table.c.revision, table.c.available, table.c.reason)
                    .where(table.c.scope_id == scope_id, table.c.node_id == node_id)
                    .order_by(table.c.sequence.desc())
                    .limit(1)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return LifecycleEventRecord(
            sequence=int(row["sequence"]),
            revision=int(row["revision"]),
            available=bool(row["available"]),
            reason=str(row["reason"]),
        )

    async def add_event(
        self,
        connection: AsyncConnection,
        scope_id: str,
        node_id: str,
        event: LifecycleEventRecord,
        /,
    ) -> None:
        await connection.execute(
            insert(SOURCE_LIFECYCLE_EVENTS_TABLE).values(
                scope_id=scope_id,
                node_id=node_id,
                sequence=event.sequence,
                revision=event.revision,
                available=event.available,
                reason=event.reason,
            )
        )

    async def set_available(
        self,
        connection: AsyncConnection,
        scope_id: str,
        node: LifecycleNode,
        available: bool,
        /,
    ) -> None:
        """Store a derived availability; a changed Memory node also awaits native synchronization."""

        table = SOURCE_LIFECYCLE_NODES_TABLE
        await connection.execute(
            update(table)
            .where(table.c.scope_id == scope_id, table.c.node_id == node.node_id)
            .values(available=available, native_pending=node.native_pending or node.kind == "memory")
        )

    async def pending_memory_entries(self, connection: AsyncConnection, scope_id: str, /) -> tuple[str, ...]:
        table = SOURCE_LIFECYCLE_NODES_TABLE
        rows = await connection.execute(
            select(table.c.target_id)
            .where(table.c.scope_id == scope_id, table.c.native_pending.is_(True), table.c.kind == "memory")
            .distinct()
        )
        return tuple(sorted(str(row[0]) for row in rows))

    async def entry_availability(
        self,
        connection: AsyncConnection,
        scope_id: str,
        entry_id: str,
        /,
    ) -> bool:
        """Return whether every node bound to one Memory entry is available."""

        table = SOURCE_LIFECYCLE_NODES_TABLE
        rows = await connection.execute(
            select(table.c.available).where(
                table.c.scope_id == scope_id,
                table.c.kind == "memory",
                table.c.target_id == entry_id,
            )
        )
        return all(bool(row[0]) for row in rows)

    async def settle_entry(self, connection: AsyncConnection, scope_id: str, entry_id: str, /) -> None:
        table = SOURCE_LIFECYCLE_NODES_TABLE
        await connection.execute(
            update(table)
            .where(table.c.scope_id == scope_id, table.c.kind == "memory", table.c.target_id == entry_id)
            .values(native_pending=False)
        )


async def without_withheld_topics(
    connection: AsyncConnection,
    scope_id: str,
    channels: TopicMemorySearchChannels,
    /,
) -> TopicMemorySearchChannels:
    """Remove Topic revisions whose governing lifecycle registration is unavailable.

    A registration governs its exact revision and every later revision of the same
    Topic until a newer revision is registered, because a revision carries forward
    the content of the one it replaces.
    """

    candidates: dict[str, set[int]] = {}
    for name in _TOPIC_CHANNELS:
        for hit in getattr(channels, name):
            candidates.setdefault(hit.artifact_ref.artifact_id, set()).add(hit.artifact_ref.revision)
    if not candidates:
        return channels
    table = SOURCE_LIFECYCLE_NODES_TABLE
    rows = await connection.execute(
        select(table.c.target_id, table.c.target_revision, table.c.available).where(
            table.c.scope_id == scope_id,
            table.c.kind == "topic",
            table.c.target_id.in_(sorted(candidates)),
        )
    )
    registrations: dict[str, dict[int, bool]] = {}
    for target_id, target_revision, available in rows:
        revisions = registrations.setdefault(str(target_id), {})
        revisions[int(target_revision)] = revisions.get(int(target_revision), True) and bool(available)
    withheld: set[tuple[str, int]] = set()
    for artifact_id, revisions in registrations.items():
        for revision in candidates[artifact_id]:
            governing = max((registered for registered in revisions if registered <= revision), default=None)
            if governing is not None and not revisions[governing]:
                withheld.add((artifact_id, revision))
    if not withheld:
        return channels
    return channels.model_copy(
        update={
            name: tuple(
                hit
                for hit in getattr(channels, name)
                if (hit.artifact_ref.artifact_id, hit.artifact_ref.revision) not in withheld
            )
            for name in _TOPIC_CHANNELS
        }
    )


def _node(row) -> LifecycleNode:
    node_id = str(row["node_id"])
    kind = str(row["kind"])
    model = _REFERENCE_MODELS.get(kind)
    if model is None:
        raise InvalidStoredPayloadError("source-lifecycle", node_id, "node kind is unknown")
    try:
        parents = _PARENTS.validate_json(stored_bytes(row["parents"], column="parents"), strict=True)
    except ValidationError as error:
        raise InvalidStoredPayloadError("source-lifecycle", node_id, "parents do not match the model") from error
    return LifecycleNode(
        node_id=node_id,
        kind=cast(LifecycleNodeKind, kind),
        reference=load_model(
            model,
            stored_bytes(row["reference"], column="reference"),
            kind="source-lifecycle",
            name=node_id,
        ),
        parents=parents,
        policy=None if row["policy"] is None else cast(LifecyclePolicy, str(row["policy"])),
        lifecycle_revision=None if row["lifecycle_revision"] is None else int(row["lifecycle_revision"]),
        available=bool(row["available"]),
        native_pending=bool(row["native_pending"]),
    )


__all__ = [
    "LifecycleEventRecord",
    "LifecycleNode",
    "LifecycleNodeKind",
    "LifecyclePolicy",
    "LifecycleReference",
    "SourceLifecycleRepository",
    "without_withheld_topics",
]
