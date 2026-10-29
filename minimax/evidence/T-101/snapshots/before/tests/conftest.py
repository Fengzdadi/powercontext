"""测试夹具：每个测试拿到一份新的种子数据和固定日期 2026-10-15。"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit

import pytest

from library.api.app import create_app
from library.clock import FixedClock
from library.repository import Repository

TODAY = date(2026, 10, 15)


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    json: dict


class TestClient:
    """直接调用 WSGI 应用，不经过网络。"""

    __test__ = False

    def __init__(self, app) -> None:
        self.app = app

    def request(self, method: str, url: str, body: dict | None = None) -> Response:
        parts = urlsplit(url)
        raw = json.dumps(body).encode("utf-8") if body is not None else b""
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": parts.path,
            "QUERY_STRING": parts.query,
            "CONTENT_LENGTH": str(len(raw)),
            "wsgi.input": io.BytesIO(raw),
        }
        captured: dict = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            captured["status"] = int(status.split()[0])
            captured["headers"] = dict(headers)

        payload = b"".join(self.app(environ, start_response))
        return Response(captured["status"], captured["headers"], json.loads(payload.decode("utf-8")))

    def get(self, url: str) -> Response:
        return self.request("GET", url)

    def post(self, url: str, body: dict | None = None) -> Response:
        return self.request("POST", url, body)


@pytest.fixture
def repo() -> Repository:
    return Repository.from_seed()


@pytest.fixture
def client(repo: Repository) -> TestClient:
    return TestClient(create_app(repo, FixedClock(TODAY)))


def ids(response: Response) -> list[str]:
    return [item["id"] for item in response.json["items"]]
