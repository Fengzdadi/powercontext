"""逾期罚款。"""

from __future__ import annotations

from datetime import date

FINE_PER_DAY_CENTS = 50


def overdue_fine_cents(due_on: date, returned_on: date, price_cents: int) -> int:
    """按逾期天数计算罚款（单位：分），不超过图书定价。

    实现: FINE-001, FINE-002, FINE-003
    """
    days_late = (returned_on - due_on).days
    if days_late <= 0:
        return 0
    return min(days_late * FINE_PER_DAY_CENTS, price_cents)
