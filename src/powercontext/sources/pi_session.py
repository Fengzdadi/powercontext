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

"""Captured visible events of one Pi session branch and their resumable import.

A Pi v3 session is JSONL: a ``session`` header followed by entries linked through
``parentId``. A selected leaf and its ancestors form one history path. Every visible event on
that path becomes one immutable Source holding the complete entry record, including events
that a later compaction or branch summary replaced in the model context.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, cast
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from powercontext.errors import InvalidConnectorRunError
from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources.connectors import (
    ConnectorRunCompletion,
    ConnectorRunSession,
    ConnectorRunStatus,
    ConnectorSubmissionStatus,
)
from powercontext.sources.definitions import SourceDefinition, SourceProjection
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence

PI_EVENT_SOURCE_NAME = "pi-event"
PI_SESSION_CONNECTOR_NAME = "pi-session-history"
_SESSION_VERSION = 3
_UNKNOWN_LABEL = "unknown"

_Record = dict[str, JsonValue]


class PiSessionInput(BaseModel):
    """Complete Pi v3 JSONL bytes and the leaf whose ancestor path is read."""

    content: bytes
    leaf_id: str | None = None

    def __init__(self, content: bytes, leaf_id: str | None = None) -> None:
        """Accept the documented ``PiSessionInput(content, leaf_id=None)`` call form."""

        super().__init__(content=content, leaf_id=leaf_id)


class PiEventInput(BaseModel):
    """One visible event of the selected branch with its complete session record."""

    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: _Record


class PiEventSource(Source):
    """A captured Pi event identified only by its session and event IDs."""

    materialization: Literal[SourceMaterialization.CAPTURED] = SourceMaterialization.CAPTURED
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: _Record


@dataclass(frozen=True, slots=True)
class _SessionGraph:
    """A fully validated session file: its header ID and entries in file order."""

    session_id: str
    entries: dict[str, _Record]

    def path_to(self, leaf_id: str | None) -> tuple[_Record, ...]:
        """Return the root-to-leaf ancestor path; no leaf selects the last entry."""

        if leaf_id is None:
            if not self.entries:
                return ()
            leaf_id = next(reversed(self.entries))
        elif leaf_id not in self.entries:
            raise ValueError(f"Pi session has no entry {leaf_id!r} to use as the leaf")  # noqa: TRY003
        path: list[_Record] = []
        current: str | None = leaf_id
        # Parents always precede their children, so this walk terminates.
        while current is not None:
            entry = self.entries[current]
            path.append(entry)
            current = cast(str | None, entry["parentId"])
        path.reverse()
        return tuple(path)

    def events(self, leaf_id: str | None) -> tuple[PiEventInput, ...]:
        events: list[PiEventInput] = []
        for entry in self.path_to(leaf_id):
            visible = _visible_text(entry)
            if visible is None:
                continue
            role, body = visible
            events.append(
                PiEventInput(
                    session_id=self.session_id,
                    event_id=cast(str, entry["id"]),
                    parent_id=cast(str | None, entry["parentId"]),
                    event_type=cast(str, entry["type"]),
                    role=role,
                    content=f"{role}: {body}",
                    record=entry,
                )
            )
        return tuple(events)


def parse_pi_session(value: PiSessionInput) -> tuple[PiEventInput, ...]:
    """Return the visible events from root to the selected leaf, or raise ``ValueError``.

    The whole file is validated before any event is returned. Control entries keep the
    branch connected but produce no events; thinking and image content never enter text.
    """

    return _read_session(value.content).events(value.leaf_id)


def _read_session(content: bytes) -> _SessionGraph:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Pi session must be valid UTF-8") from error  # noqa: TRY003
    session_id: str | None = None
    entries: dict[str, _Record] = {}
    # JSONL records end at LF only; JSON strings may contain other Unicode line breaks.
    for line_number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        record = _json_object(line, line_number)
        if session_id is None:
            session_id = _session_id(record)
            continue
        entry_id = record.get("id")
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError(f"Pi session line {line_number} must have a non-empty string id")  # noqa: TRY003
        if entry_id in entries:
            raise ValueError(f"Pi session line {line_number} repeats entry id {entry_id!r}")  # noqa: TRY003
        if "parentId" not in record:
            raise ValueError(f"Pi session line {line_number} must declare parentId")  # noqa: TRY003
        parent_id = record["parentId"]
        if parent_id is not None and (not isinstance(parent_id, str) or parent_id not in entries):
            problem = "refers to the entry itself" if parent_id == entry_id else "is not an earlier entry"
            raise ValueError(f"Pi session line {line_number} parentId {parent_id!r} {problem}")  # noqa: TRY003
        entries[entry_id] = record
    if session_id is None:
        raise ValueError("Pi session must start with a session header")  # noqa: TRY003
    return _SessionGraph(session_id=session_id, entries=entries)


def _json_object(line: str, line_number: int) -> _Record:
    try:
        value = json.loads(line, parse_constant=_reject_json_constant)
    except (ValueError, RecursionError) as error:
        raise ValueError(f"Pi session line {line_number} is not valid JSON") from error  # noqa: TRY003
    if isinstance(value, dict):
        return value
    raise ValueError(f"Pi session line {line_number} must be a JSON object")  # noqa: TRY003


def _reject_json_constant(name: str) -> None:
    raise ValueError(f"{name} is not a JSON value")  # noqa: TRY003


def _session_id(header: _Record) -> str:
    version = header.get("version")
    if header.get("type") != "session" or type(version) is not int or version != _SESSION_VERSION:
        raise ValueError(f"Pi session must start with a version {_SESSION_VERSION} session header")  # noqa: TRY003
    session_id = header.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("Pi session header id must be a non-empty string")  # noqa: TRY003
    return session_id


def _visible_text(entry: _Record) -> tuple[str, str] | None:
    """Return ``(role, body)`` for an entry with visible text, otherwise ``None``."""

    event_type = entry.get("type")
    visible: tuple[str, str] | None = None
    if event_type == "message":
        message = entry.get("message")
        if isinstance(message, dict):
            visible = _message_text(message)
    elif event_type in {"compaction", "branch_summary"}:
        summary = entry.get("summary")
        if isinstance(summary, str):
            visible = (cast(str, event_type), summary)
    elif event_type == "custom_message":
        visible = ("custom", _content_text(entry.get("content")))
    if visible is None or not visible[1].strip():
        return None
    return visible


def _message_text(message: _Record) -> tuple[str, str] | None:
    role = message.get("role")
    if not isinstance(role, str) or not role:
        return None
    if role == "toolResult":
        label = f"[tool_result {_label(message.get('toolName'))} {_label(message.get('toolCallId'))}]"
        return role, f"{label} {_content_text(message.get('content'))}"
    if role == "bashExecution":
        return role, f"$ {_string(message.get('command'))}\n{_string(message.get('output'))}"
    return role, _content_text(message.get("content"))


def _content_text(content: JsonValue) -> str:
    """Render string content verbatim and join visible text and tool-call blocks by newline."""

    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        text = block.get("text")
        if block_type == "text" and isinstance(text, str):
            parts.append(text)
        elif block_type == "toolCall":
            arguments = json.dumps(
                block.get("arguments", {}),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            parts.append(f"[tool_call {_label(block.get('name'))} {_label(block.get('id'))}] {arguments}")
    return "\n".join(parts)


def _label(value: JsonValue) -> str:
    return value if isinstance(value, str) else _UNKNOWN_LABEL


def _string(value: JsonValue) -> str:
    return value if isinstance(value, str) else ""


def _event_source_id(session_id: str, event_id: str) -> str:
    """Derive a stable identity from the session and event IDs alone.

    Percent-encoding keeps the readable form injective; identities that would exceed the
    Source ID bound use a digest form whose distinct prefix cannot meet a readable one.
    """

    if not session_id or not event_id:
        raise ValueError("Pi event identity requires non-empty session_id and event_id")  # noqa: TRY003
    readable = f"pi:{quote(session_id, safe='')}:{quote(event_id, safe='')}"
    if len(readable) <= MAX_SOURCE_ID_LENGTH:
        return readable
    digest = hashlib.sha256(json.dumps([session_id, event_id]).encode()).hexdigest()
    return f"pi-sha256:{digest}"


class PiEventTextEvidenceProjection:
    """Expose the complete event text and its branch identity as text evidence."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PiEventSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PI_EVENT_SOURCE_NAME,
            source_id=source.name,
            content=source.content,
            metadata={
                "session_id": source.session_id,
                "event_id": source.event_id,
                "parent_id": source.parent_id,
                "event_type": source.event_type,
                "role": source.role,
            },
        )


class PiEventSourceDefinition:
    """Resolve visible Pi events into captured Sources and read them back exactly."""

    input_class = PiEventInput
    name = PI_EVENT_SOURCE_NAME
    version = "1"
    source_class = PiEventSource

    def __init__(self) -> None:
        projection = cast(SourceProjection[PiEventSource], PiEventTextEvidenceProjection())
        self.projections: tuple[SourceProjection[PiEventSource], ...] = (projection,)

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        return PiEventSource(
            name=_event_source_id(value.session_id, value.event_id),
            session_id=value.session_id,
            event_id=value.event_id,
            parent_id=value.parent_id,
            event_type=value.event_type,
            role=value.role,
            content=value.content,
            record=value.record,
        )

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return PiEventInput(
            session_id=source.session_id,
            event_id=source.event_id,
            parent_id=source.parent_id,
            event_type=source.event_type,
            role=source.role,
            content=source.content,
            record=source.record,
        )


PI_EVENT_SOURCE_DEFINITION: SourceDefinition[PiEventInput, PiEventSource, PiEventInput] = PiEventSourceDefinition()

_RecordDigest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _PiSessionCheckpoint(BaseModel):
    """Imported event IDs per session with a digest of each imported entry record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["powercontext.pi-session-history/1"] = "powercontext.pi-session-history/1"
    sessions: dict[str, dict[str, _RecordDigest]] = Field(default_factory=dict)


class PiSessionConnector:
    """Import the not-yet-imported visible events of one Pi session file branch.

    Each run parses the complete file and verifies every previously imported entry still in
    it before submitting anything, so a malformed file or a rewritten imported entry fails
    the run and the lifecycle keeps the committed checkpoint. Events imported from other
    branches stay in the checkpoint; a shared ancestor is never submitted twice.
    """

    name = PI_SESSION_CONNECTOR_NAME
    version = "1"
    source_definitions = frozenset({PI_EVENT_SOURCE_NAME})

    def __init__(self, path: str | os.PathLike[str], leaf_id: str | None = None) -> None:
        self._path = Path(path)
        self._leaf_id = leaf_id

    async def run(self, session: ConnectorRunSession, /) -> ConnectorRunCompletion:
        checkpoint = _load_checkpoint(session.checkpoint)
        graph, events = await asyncio.to_thread(self._read)
        imported = checkpoint.sessions.get(graph.session_id, {})
        for entry_id, digest in imported.items():
            entry = graph.entries.get(entry_id)
            if entry is not None and _record_digest(entry) != digest:
                raise ValueError(f"Pi session entry {entry_id!r} changed after it was imported")  # noqa: TRY003

        accepted: dict[str, str] = {}
        complete = True
        for event in events:
            if event.event_id in imported:
                continue
            outcome = await session.submit(
                _event_source_id(event.session_id, event.event_id),
                PI_EVENT_SOURCE_NAME,
                event,
            )
            if outcome.status is ConnectorSubmissionStatus.ACCEPTED:
                accepted[event.event_id] = _record_digest(graph.entries[event.event_id])
            else:
                complete = False

        status = ConnectorRunStatus.COMPLETE if complete else ConnectorRunStatus.INCOMPLETE
        if not accepted:
            return ConnectorRunCompletion(status=status, checkpoint=session.checkpoint)
        sessions = {**checkpoint.sessions, graph.session_id: {**imported, **accepted}}
        next_checkpoint = _PiSessionCheckpoint(sessions=sessions)
        return ConnectorRunCompletion(status=status, checkpoint=next_checkpoint.model_dump(mode="json"))

    def _read(self) -> tuple[_SessionGraph, tuple[PiEventInput, ...]]:
        graph = _read_session(self._path.read_bytes())
        return graph, graph.events(self._leaf_id)


def _load_checkpoint(value: JsonValue | None) -> _PiSessionCheckpoint:
    if value is None:
        return _PiSessionCheckpoint()
    try:
        return _PiSessionCheckpoint.model_validate(value)
    except ValidationError as error:
        raise InvalidConnectorRunError("checkpoint", "is not a pi-session-history checkpoint") from error


def _record_digest(record: _Record) -> str:
    """Digest the parsed entry so formatting-only rewrites keep the same value."""

    encoded = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


__all__ = [
    "PI_EVENT_SOURCE_DEFINITION",
    "PI_EVENT_SOURCE_NAME",
    "PI_SESSION_CONNECTOR_NAME",
    "PiEventInput",
    "PiEventSource",
    "PiEventSourceDefinition",
    "PiEventTextEvidenceProjection",
    "PiSessionConnector",
    "PiSessionInput",
    "parse_pi_session",
]
