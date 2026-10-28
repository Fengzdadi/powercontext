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

"""Captured row Sources parsed from offline CSV documents and keyed by primary key."""

from __future__ import annotations

import csv
import io
import json
from typing import Literal, cast
from urllib.parse import quote

from pydantic import BaseModel, JsonValue

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources.definitions import SourceDefinition, SourceProjection
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence

CSV_ROW_SOURCE_NAME = "csv-row"


class CSVDocumentInput(BaseModel):
    """One complete offline CSV document whose records are keyed by one header field."""

    document_id: str
    primary_key: str
    content: bytes


class CSVRowInput(BaseModel):
    """One data record with the document header order and verbatim field values."""

    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


class CSVRowSource(Source):
    """A captured CSV record identified by its document and primary-key value."""

    materialization: Literal[SourceMaterialization.CAPTURED] = SourceMaterialization.CAPTURED
    source_id: str
    document_id: str
    primary_key: str
    primary_key_value: str
    columns: tuple[str, ...]
    values: tuple[str, ...]


def parse_csv_document(value: CSVDocumentInput) -> tuple[CSVRowInput, ...]:
    """Parse and validate a whole document before returning any of its rows.

    Records follow ``csv.reader`` with the default comma dialect and ``strict=True``. The
    first record is the header; empty physical records after it are ignored. Fields stay
    verbatim strings, and every failure raises ``ValueError`` without partial results.
    """

    _validate_document_id(value.document_id)
    if not value.primary_key:
        raise ValueError("CSV primary_key must be non-empty")  # noqa: TRY003
    try:
        text = value.content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CSV content must be valid UTF-8") from error  # noqa: TRY003

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader, None)
        if not header:
            raise ValueError("CSV document must start with a non-empty header record")  # noqa: TRY003
        columns = tuple(header)
        key_index = _primary_key_index(columns, value.primary_key)
        rows: list[CSVRowInput] = []
        seen_keys: set[str] = set()
        for record in reader:
            if not record:
                continue
            if len(record) != len(columns):
                raise ValueError(  # noqa: TRY003
                    f"CSV record ending at line {reader.line_num} has {len(record)} fields, expected {len(columns)}"
                )
            key_value = record[key_index]
            if key_value in seen_keys:
                raise ValueError(f"CSV primary key value {key_value!r} is not unique")  # noqa: TRY003
            seen_keys.add(key_value)
            # Validates the key value and the identity bound before any row is returned.
            csv_row_source_id(value.document_id, key_value)
            rows.append(
                CSVRowInput(
                    document_id=value.document_id,
                    primary_key=value.primary_key,
                    primary_key_value=key_value,
                    columns=columns,
                    values=tuple(record),
                )
            )
    except csv.Error as error:
        raise ValueError(f"malformed CSV at line {reader.line_num}: {error}") from error  # noqa: TRY003
    return tuple(rows)


def csv_row_source_id(document_id: str, primary_key_value: str) -> str:
    """Return ``csv:{document_id}:{primary_key_value}`` with each part percent-encoded."""

    _validate_document_id(document_id)
    if not isinstance(primary_key_value, str) or not primary_key_value.strip():
        raise ValueError("CSV primary key value must not be empty or blank")  # noqa: TRY003
    source_id = f"csv:{quote(document_id, safe='')}:{quote(primary_key_value, safe='')}"
    if len(source_id) > MAX_SOURCE_ID_LENGTH:
        raise ValueError(f"CSV row source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters")  # noqa: TRY003
    return source_id


class CSVRowTextEvidenceProjection:
    """Expose one row as a header-ordered JSON object through standard text evidence."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = CSVRowSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: CSVRowSource, /) -> TextEvidence:
        row: dict[str, JsonValue] = dict(zip(source.columns, source.values, strict=True))
        return TextEvidence(
            source_type=CSV_ROW_SOURCE_NAME,
            source_id=source.name,
            content=json.dumps(row, ensure_ascii=False, separators=(",", ":")),
            metadata={
                "document_id": source.document_id,
                "primary_key": source.primary_key,
                "primary_key_value": source.primary_key_value,
                "columns": list(source.columns),
                "row": row,
            },
        )


class CSVRowSourceDefinition:
    """Resolve CSV records into captured row Sources and read them back exactly."""

    input_class = CSVRowInput
    name = CSV_ROW_SOURCE_NAME
    version = "1"
    source_class = CSVRowSource

    def __init__(self) -> None:
        projection = cast(SourceProjection[CSVRowSource], CSVRowTextEvidenceProjection())
        self.projections: tuple[SourceProjection[CSVRowSource], ...] = (projection,)

    async def resolve(self, value: CSVRowInput, /) -> CSVRowSource:
        source_id = csv_row_source_id(value.document_id, value.primary_key_value)
        if len(value.values) != len(value.columns):
            raise ValueError("CSV row values must match its columns")  # noqa: TRY003
        if value.values[_primary_key_index(value.columns, value.primary_key)] != value.primary_key_value:
            raise ValueError("CSV row primary_key_value must equal its primary key field")  # noqa: TRY003
        return CSVRowSource(
            name=source_id,
            source_id=source_id,
            document_id=value.document_id,
            primary_key=value.primary_key,
            primary_key_value=value.primary_key_value,
            columns=value.columns,
            values=value.values,
        )

    async def read(self, source: CSVRowSource, /) -> CSVRowInput:
        return CSVRowInput(
            document_id=source.document_id,
            primary_key=source.primary_key,
            primary_key_value=source.primary_key_value,
            columns=source.columns,
            values=source.values,
        )


def _validate_document_id(document_id: object) -> None:
    if not isinstance(document_id, str) or not document_id or document_id != document_id.strip():
        raise ValueError("CSV document_id must be non-empty without leading or trailing whitespace")  # noqa: TRY003


def _primary_key_index(columns: tuple[str, ...], primary_key: str) -> int:
    """Validate header fields and locate the exactly matching primary-key field."""

    if not columns:
        raise ValueError("CSV header must contain at least one field")  # noqa: TRY003
    if any(not column.strip() for column in columns):
        raise ValueError("CSV header fields must not be empty or blank")  # noqa: TRY003
    if len(set(columns)) != len(columns):
        raise ValueError("CSV header fields must be unique")  # noqa: TRY003
    if not primary_key or primary_key not in columns:
        raise ValueError(f"CSV primary key {primary_key!r} is not a header field")  # noqa: TRY003
    return columns.index(primary_key)


CSV_ROW_SOURCE_DEFINITION: SourceDefinition[CSVRowInput, CSVRowSource, CSVRowInput] = CSVRowSourceDefinition()

__all__ = [
    "CSV_ROW_SOURCE_DEFINITION",
    "CSV_ROW_SOURCE_NAME",
    "CSVDocumentInput",
    "CSVRowInput",
    "CSVRowSource",
    "CSVRowSourceDefinition",
    "CSVRowTextEvidenceProjection",
    "csv_row_source_id",
    "parse_csv_document",
]
