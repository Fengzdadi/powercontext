"""Unit tests for ingest validation (no DB access needed — validation
runs before any DB call)."""
import pytest

from examradar.ingest import validate_input, ValidationError, MAX_FILE_SIZE


def test_valid_kind_and_extension():
    validate_input("note.md", "notes", b"x")


def test_invalid_kind():
    with pytest.raises(ValidationError, match="doc_kind"):
        validate_input("note.md", "syllabus", b"x")


def test_invalid_extension():
    with pytest.raises(ValidationError, match="文件只支持"):
        validate_input("photo.jpg", "notes", b"x")


def test_no_extension():
    with pytest.raises(ValidationError):
        validate_input("README", "notes", b"x")


def test_file_too_large():
    with pytest.raises(ValidationError, match="30 MB"):
        validate_input("big.md", "notes", b"x" * (MAX_FILE_SIZE + 1))


def test_boundary_size_ok():
    validate_input("big.md", "notes", b"x" * 1024)


def test_all_allowed_kinds():
    for kind in ("notes", "slides", "paper", "exam"):
        validate_input("f.md", kind, b"x")
