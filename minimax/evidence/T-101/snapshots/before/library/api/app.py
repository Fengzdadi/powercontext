"""WSGI 应用：路由、请求解析和错误响应。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import parse_qsl

from ..clock import Clock, SystemClock
from ..errors import InvalidParameter, LibraryError, NotFound
from ..repository import Repository
from . import handlers

ROUTES: list[tuple[str, re.Pattern[str], Callable[..., tuple[int, dict]]]] = [
    ("GET", re.compile(r"/books"), handlers.list_books),
    ("GET", re.compile(r"/books/(?P<book_id>[^/]+)"), handlers.get_book),
    ("POST", re.compile(r"/loans"), handlers.create_loan),
    ("POST", re.compile(r"/loans/(?P<loan_id>[^/]+)/return"), handlers.return_loan),
    ("POST", re.compile(r"/loans/(?P<loan_id>[^/]+)/renew"), handlers.renew_loan),
    ("GET", re.compile(r"/members/(?P<member_id>[^/]+)/loans"), handlers.member_loans),
]


@dataclass
class AppContext:
    repo: Repository
    clock: Clock


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, str]
    body: bytes = b""

    def json(self) -> dict:
        try:
            data = json.loads(self.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise InvalidParameter("body", "请求体必须是 JSON 对象") from None
        if not isinstance(data, dict):
            raise InvalidParameter("body", "请求体必须是 JSON 对象")
        return data


def parse_query(query_string: str) -> dict[str, str]:
    """解析查询串，同名参数只取第一个值。

    实现: API-005
    """
    params: dict[str, str] = {}
    for key, value in parse_qsl(query_string, keep_blank_values=True):
        params.setdefault(key, value)
    return params


class LibraryApp:
    """WSGI 入口。

    实现: API-001, API-002
    """

    def __init__(self, repo: Repository, clock: Clock) -> None:
        self.context = AppContext(repo=repo, clock=clock)

    def __call__(self, environ: dict, start_response: Callable) -> Iterable[bytes]:
        length = int(environ.get("CONTENT_LENGTH") or 0)
        request = Request(
            method=environ.get("REQUEST_METHOD", "GET").upper(),
            path=environ.get("PATH_INFO", "/") or "/",
            query=parse_query(environ.get("QUERY_STRING", "")),
            body=environ["wsgi.input"].read(length) if length else b"",
        )
        try:
            status, payload = self.dispatch(request)
        except LibraryError as exc:
            status, payload = exc.status, exc.to_dict()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        start_response(
            f"{status} {HTTPStatus(status).phrase}",
            [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))],
        )
        return [body]

    def dispatch(self, request: Request) -> tuple[int, dict]:
        for method, pattern, handler in ROUTES:
            match = pattern.fullmatch(request.path)
            if match and method == request.method:
                return handler(self.context, request, **match.groupdict())
        raise NotFound(f"没有这个接口：{request.method} {request.path}")


def create_app(repo: Repository | None = None, clock: Clock | None = None) -> LibraryApp:
    return LibraryApp(repo or Repository.from_seed(), clock or SystemClock())
