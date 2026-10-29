from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2] / "project"


@pytest.fixture
def project_dir() -> Path:
    return PROJECT
