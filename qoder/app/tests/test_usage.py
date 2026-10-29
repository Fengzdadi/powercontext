"""Unit tests for usage statistics (time-zone bucketing, study-time estimate)."""
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from examradar.seekdb import compute_usage_stats


def _cfg(gap=30, per_event=1.0):
    return SimpleNamespace(usage_session_gap_minutes=gap,
                           usage_minutes_per_event=per_event)


def _event(dt_iso, event="search", session_id=None):
    return {"event": event, "session_id": session_id,
            "created_at": dt_iso}


class TestDailyBucketing:
    def test_utc_day(self):
        events = [_event("2026-10-28T12:00:00+00:00")]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg())
        assert [d["date"] for d in stats["daily"]] == ["2026-10-28"]

    def test_new_york_evening_utc_is_same_local_day(self):
        # 2026-10-28 23:30 New York (EDT, UTC-4) = 2026-10-29 03:30 UTC.
        # The old tz_offset_minutes implementation flipped the sign and
        # bucketed this into 10-28; zoneinfo gets the local day right.
        events = [_event("2026-10-29T03:30:00+00:00")]
        stats = compute_usage_stats(events, ZoneInfo("America/New_York"), _cfg())
        assert stats["daily"][0]["date"] == "2026-10-28"

    def test_utc_morning_lands_on_previous_new_york_day(self):
        # 2026-10-28 03:30 UTC = 2026-10-27 23:30 EDT
        events = [_event("2026-10-28T03:30:00+00:00")]
        stats = compute_usage_stats(events, ZoneInfo("America/New_York"), _cfg())
        assert stats["daily"][0]["date"] == "2026-10-27"

    def test_shanghai_rolls_to_next_day(self):
        # 2026-10-28 16:30 UTC = 2026-10-29 00:30 +08
        events = [_event("2026-10-28T16:30:00+00:00")]
        stats = compute_usage_stats(events, ZoneInfo("Asia/Shanghai"), _cfg())
        assert stats["daily"][0]["date"] == "2026-10-29"

    def test_dst_fall_back_keeps_correct_local_date(self):
        # US DST ends 2026-11-01: 05:30 UTC is 01:30 EDT, 06:30 UTC is
        # 01:30 EST — both are the same local day.
        events = [
            _event("2026-11-01T05:30:00+00:00"),
            _event("2026-11-01T06:30:00+00:00"),
        ]
        stats = compute_usage_stats(events, ZoneInfo("America/New_York"), _cfg())
        assert [d["date"] for d in stats["daily"]] == ["2026-11-01"]

    def test_events_bucketed_by_local_day(self):
        events = [
            _event("2026-10-28T02:00:00+00:00", "import"),   # 10-27 NY
            _event("2026-10-28T20:00:00+00:00", "search"),   # 10-28 NY
            _event("2026-10-29T02:00:00+00:00", "search"),   # 10-28 NY
        ]
        stats = compute_usage_stats(events, ZoneInfo("America/New_York"), _cfg())
        days = {d["date"]: d for d in stats["daily"]}
        assert days["2026-10-27"]["import"] == 1
        assert days["2026-10-28"]["search"] == 2
        assert days["2026-10-28"]["total"] == 2


class TestStudyMinutes:
    def test_single_event_counts_minimum(self):
        events = [_event("2026-10-28T12:00:00+00:00")]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg())
        assert stats["study_minutes"] == 1.0

    def test_events_within_gap_form_one_segment(self):
        events = [
            _event("2026-10-28T12:00:00+00:00"),
            _event("2026-10-28T12:10:00+00:00"),
            _event("2026-10-28T12:20:00+00:00"),
        ]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg())
        # 20 min span vs 3 events x 1 min -> span wins
        assert stats["study_minutes"] == 20.0

    def test_gap_splits_segments(self):
        events = [
            _event("2026-10-28T12:00:00+00:00"),
            _event("2026-10-28T13:00:00+00:00"),  # 60 min gap > 30
        ]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg())
        # two segments of one event each -> 1 + 1 = 2
        assert stats["study_minutes"] == 2.0

    def test_min_per_event_wins_over_tiny_span(self):
        events = [
            _event("2026-10-28T12:00:00+00:00"),
            _event("2026-10-28T12:00:30+00:00"),  # 0.5 min span
        ]
        stats = compute_usage_stats(events, ZoneInfo("UTC"),
                                    _cfg(per_event=5.0))
        assert stats["study_minutes"] == 10.0


class TestCounts:
    def test_event_type_counts_and_sessions(self):
        events = [
            _event("2026-10-28T12:00:00+00:00", "search", "s1"),
            _event("2026-10-28T12:05:00+00:00", "search", "s1"),
            _event("2026-10-28T13:00:00+00:00", "analyze", "s2"),
            _event("2026-10-28T14:00:00+00:00", "quiz"),
        ]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg())
        assert stats["search_count"] == 2
        assert stats["analyze_count"] == 1
        assert stats["quiz_count"] == 1
        assert stats["total_events"] == 4
        assert stats["session_count"] == 2
