"""查询参数解析。参数表是 `dict[str, str]`，同名参数只保留第一个值（见 app.parse_query）。"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from ..errors import InvalidParameter

_INT_PATTERN = re.compile(r"[+-]?[0-9]+")
_TRUE_VALUES = {"true", "1"}
_FALSE_VALUES = {"false", "0"}


def parse_bool(params: Mapping[str, str], name: str) -> bool | None:
    """解析布尔查询参数；参数没有出现时返回 None。

    实现: API-003
    """
    if name not in params:
        return None
    value = params[name].strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise InvalidParameter(name, f"{name} 只能是 true、false、1 或 0")


def parse_int(
    params: Mapping[str, str],
    name: str,
    *,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    """解析整数查询参数并检查范围；参数没有出现时返回 default。

    实现: API-004
    """
    if name not in params:
        return default
    raw = params[name].strip()
    if not _INT_PATTERN.fullmatch(raw):
        raise InvalidParameter(name, f"{name} 必须是整数")
    value = int(raw)
    if minimum is not None and value < minimum:
        raise InvalidParameter(name, f"{name} 不能小于 {minimum}")
    if maximum is not None and value > maximum:
        raise InvalidParameter(name, f"{name} 不能大于 {maximum}")
    return value


def parse_choice(params: Mapping[str, str], name: str, choices: Iterable[str], default: str) -> str:
    """解析枚举查询参数。

    实现: API-002
    """
    if name not in params:
        return default
    value = params[name]
    allowed = list(choices)
    if value not in allowed:
        raise InvalidParameter(name, f"{name} 只能是 {', '.join(allowed)} 之一")
    return value
