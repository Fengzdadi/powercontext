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

"""Transfer prepared context as verifiable chunked packs and prefix-reuse deltas.

A full :class:`ContextPack` carries the UTF-8 bytes of one prepared context as ordered chunks. A
:class:`ContextPackDelta` lets a receiver that already holds the previous pack keep a prefix of its
chunks and append the remaining target chunks. Both wire forms are canonical JSON (sorted keys,
``,``/``:`` separators, no extra whitespace) whose chunks are standard Base64 strings, so a receiver
can verify and rebuild a pack from serialized bytes alone.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from powercontext.errors import PowerContextError

CONTEXT_PACK_SCHEMA = "powercontext.context-pack.v1"
CONTEXT_PACK_DELTA_SCHEMA = "powercontext.context-pack-delta.v1"
DEFAULT_CHUNK_BYTES = 512

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_PACK_FIELDS = frozenset({"schema", "items", "digest", "byte_count"})
_DELTA_FIELDS = frozenset({"schema", "base_digest", "target_digest", "prefix_items", "appended"})
# A line end closes a chunk once the chunk holds at least this many bytes. Boundaries depend only on
# the bytes before them, so an unchanged context prefix always yields the same leading chunks.
_LINE_CHUNK_MIN_BYTES = 32


class ContextPackError(PowerContextError, ValueError):
    """Raised when a Context Pack, a delta, or a chunking request violates the pack protocol."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"invalid Context Pack: {code}")


@dataclass(frozen=True)
class ContextPack:
    """The complete prepared-context bytes as ordered, individually valid UTF-8 chunks."""

    items: tuple[bytes, ...]
    digest: str = field(init=False)
    byte_count: int = field(init=False)
    _wire: bytes = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        items = _chunk_tuple(self.items, "items")
        for item in items:
            try:
                item.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ContextPackError("item-encoding") from error
        encoded = [_encode_chunk(item) for item in items]
        digest = "sha256:" + hashlib.sha256(_canonical({"schema": CONTEXT_PACK_SCHEMA, "items": encoded})).hexdigest()
        wire = _self_sized({"schema": CONTEXT_PACK_SCHEMA, "items": encoded, "digest": digest})
        object.__setattr__(self, "items", items)
        object.__setattr__(self, "digest", digest)
        object.__setattr__(self, "byte_count", len(wire))
        object.__setattr__(self, "_wire", wire)

    @classmethod
    def build(cls, items: Iterable[bytes]) -> ContextPack:
        """Build a complete pack from already chunked bytes."""

        return cls(_chunk_tuple(items, "items"))

    @classmethod
    def from_content(cls, content: str | None, *, chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> ContextPack:
        """Chunk text deterministically into valid UTF-8 pieces of at most ``chunk_bytes`` bytes.

        ``None`` is the empty prepared context and yields the empty pack.
        """

        if type(chunk_bytes) is not int or chunk_bytes < 1:
            raise ContextPackError("chunk-bytes")
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise ContextPackError("content")
        try:
            encoded = content.encode("utf-8")
        except UnicodeEncodeError as error:
            raise ContextPackError("content-encoding") from error
        return cls(_split(encoded, chunk_bytes))

    @classmethod
    def from_bytes(cls, data: bytes) -> ContextPack:
        """Decode and verify one serialized pack, including its digest and byte count."""

        payload = _load(data, _PACK_FIELDS)
        if payload["schema"] != CONTEXT_PACK_SCHEMA:
            raise ContextPackError("schema")
        digest = payload["digest"]
        byte_count = payload["byte_count"]
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise ContextPackError("digest")
        if type(byte_count) is not int or byte_count < 0:
            raise ContextPackError("byte-count")
        pack = cls(_decode_chunks(payload["items"], "items"))
        if pack.digest != digest:
            raise ContextPackError("digest")
        if pack.byte_count != byte_count:
            raise ContextPackError("byte-count")
        return pack

    def to_bytes(self) -> bytes:
        return self._wire

    @property
    def content(self) -> str:
        """The reassembled UTF-8 text."""

        return b"".join(self.items).decode("utf-8")


@dataclass(frozen=True)
class ContextPackDelta:
    """Keep ``prefix_items`` chunks of the base pack, then append the remaining target chunks.

    Construction is not validated, so a decoded or hand-built delta is checked where it is used:
    :meth:`to_bytes` and :func:`apply_context_pack_delta` reject malformed fields.
    """

    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...] = ()

    def __post_init__(self) -> None:
        appended = self.appended
        if isinstance(appended, Iterable) and not isinstance(appended, (tuple, bytes, bytearray, memoryview, str)):
            object.__setattr__(self, "appended", tuple(appended))

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack) -> ContextPackDelta:
        """Reuse the common chunk prefix of ``base`` and carry the rest of ``target``."""

        if not isinstance(base, ContextPack) or not isinstance(target, ContextPack):
            raise ContextPackError("pack")
        prefix = 0
        for base_item, target_item in zip(base.items, target.items, strict=False):
            if base_item != target_item:
                break
            prefix += 1
        return cls(base.digest, target.digest, prefix, target.items[prefix:])

    @classmethod
    def from_bytes(cls, data: bytes) -> ContextPackDelta:
        payload = _load(data, _DELTA_FIELDS)
        if payload["schema"] != CONTEXT_PACK_DELTA_SCHEMA:
            raise ContextPackError("schema")
        delta = cls(
            payload["base_digest"],
            payload["target_digest"],
            payload["prefix_items"],
            _decode_chunks(payload["appended"], "appended"),
        )
        delta._validate()
        return delta

    def to_bytes(self) -> bytes:
        self._validate()
        return _canonical({
            "schema": CONTEXT_PACK_DELTA_SCHEMA,
            "base_digest": self.base_digest,
            "target_digest": self.target_digest,
            "prefix_items": self.prefix_items,
            "appended": [_encode_chunk(item) for item in self.appended],
        })

    @property
    def byte_count(self) -> int:
        return len(self.to_bytes())

    def _validate(self) -> None:
        for name, digest in (("base-digest", self.base_digest), ("target-digest", self.target_digest)):
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                raise ContextPackError(name)
        if type(self.prefix_items) is not int or self.prefix_items < 0:
            raise ContextPackError("prefix-items")
        _chunk_tuple(self.appended, "appended")


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta) -> ContextPack:
    """Rebuild and verify the target pack from the receiver's base pack and one delta."""

    if not isinstance(base, ContextPack):
        raise ContextPackError("base")
    if not isinstance(delta, ContextPackDelta):
        raise ContextPackError("delta")
    delta._validate()
    if delta.base_digest != base.digest:
        raise ContextPackError("base-digest")
    if delta.prefix_items > len(base.items):
        raise ContextPackError("prefix-items")
    target = ContextPack((*base.items[: delta.prefix_items], *delta.appended))
    if target.digest != delta.target_digest:
        raise ContextPackError("target-digest")
    return target


def _split(encoded: bytes, limit: int) -> tuple[bytes, ...]:
    chunks: list[bytes] = []
    start = 0
    size = len(encoded)
    min_line = min(_LINE_CHUNK_MIN_BYTES, limit)
    while start < size:
        end = min(start + limit, size)
        newline = encoded.find(b"\n", start + min_line - 1, end)
        if newline >= 0:
            end = newline + 1
        elif end < size:
            # Never split a multi-byte character: back off to the start of the one crossing the limit.
            while end > start and (encoded[end] & 0xC0) == 0x80:
                end -= 1
            if end == start:
                raise ContextPackError("chunk-boundary")
        chunks.append(encoded[start:end])
        start = end
    return tuple(chunks)


def _chunk_tuple(items: object, name: str) -> tuple[bytes, ...]:
    if isinstance(items, (bytes, bytearray, memoryview, str)) or not isinstance(items, Iterable):
        raise ContextPackError(name)
    chunks: list[bytes] = []
    for item in items:
        if not isinstance(item, bytes):
            raise ContextPackError(name)
        chunks.append(item)
    return tuple(chunks)


def _encode_chunk(item: bytes) -> str:
    return base64.b64encode(item).decode("ascii")


def _decode_chunks(values: object, name: str) -> tuple[bytes, ...]:
    if not isinstance(values, list):
        raise ContextPackError(name)
    chunks = []
    for value in values:
        if not isinstance(value, str):
            raise ContextPackError(name)
        try:
            chunk = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ContextPackError(f"{name}-encoding") from error
        # Standard Base64 has exactly one spelling per byte string, which keeps digests unambiguous.
        if _encode_chunk(chunk) != value:
            raise ContextPackError(f"{name}-encoding")
        chunks.append(chunk)
    return tuple(chunks)


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _self_sized(payload: dict[str, object]) -> bytes:
    """Serialize ``payload`` with a ``byte_count`` equal to the length of the result itself."""

    byte_count = 0
    while True:
        encoded = _canonical({**payload, "byte_count": byte_count})
        if len(encoded) == byte_count:
            return encoded
        byte_count = len(encoded)


def _load(data: bytes, fields: frozenset[str]) -> dict[str, Any]:
    """Decode one wire object with exactly ``fields``; callers validate each value's type."""

    if isinstance(data, str):
        data = data.encode("utf-8")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ContextPackError("payload")
    try:
        payload = json.loads(
            bytes(data).decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except ContextPackError:
        raise
    except (UnicodeDecodeError, ValueError) as error:
        raise ContextPackError("payload-encoding") from error
    if not isinstance(payload, dict):
        raise ContextPackError("payload")
    if set(payload) != fields:
        raise ContextPackError("fields")
    return payload


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload = dict(pairs)
    if len(payload) != len(pairs):
        raise ContextPackError("duplicate-field")
    return payload


def _reject_constant(value: str) -> object:
    raise ContextPackError("payload-encoding")


__all__ = [
    "CONTEXT_PACK_DELTA_SCHEMA",
    "CONTEXT_PACK_SCHEMA",
    "DEFAULT_CHUNK_BYTES",
    "ContextPack",
    "ContextPackDelta",
    "ContextPackError",
    "apply_context_pack_delta",
]
