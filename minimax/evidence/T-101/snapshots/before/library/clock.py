"""日期来源。测试用固定日期，运行时用系统日期。"""

from __future__ import annotations

from datetime import date
from typing import Protocol


class Clock(Protocol):
    def today(self) -> date: ...


class SystemClock:
    def today(self) -> date:
        return date.today()


class FixedClock:
    def __init__(self, day: date) -> None:
        self._day = day

    def today(self) -> date:
        return self._day
