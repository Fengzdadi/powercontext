"""业务错误。HTTP 层把它们转换成 API-002 规定的错误响应。"""

from __future__ import annotations


class LibraryError(Exception):
    """所有业务错误的基类。

    实现: API-002
    """

    status = 500
    code = "internal_error"

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "field": self.field}}


class InvalidParameter(LibraryError):
    """查询参数或请求体不合法（400）。"""

    status = 400
    code = "invalid_parameter"

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message, field=field)


class NotFound(LibraryError):
    """资源不存在（404）。"""

    status = 404
    code = "not_found"


class RuleViolation(LibraryError):
    """违反业务规则（409），错误码由调用方指定。"""

    status = 409

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
