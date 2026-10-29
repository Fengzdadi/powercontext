"""Unit tests for usage statistics (time-zone bucketing, session study time)."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from examradar.seekdb import compute_usage_stats


def _cfg():
    return None  # settings unused since study time comes from sessions


def _event(dt_iso, event="search", session_id=None):
    return {"event": event, "session_id": session_id,
            "created_at": dt_iso}


def _session(sid, started, ended=None, last_event=None):
    return {"session_id": sid, "started_at": started,
            "last_event_at": last_event or ended or started,
            "ended_at": ended}


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
    def test_ended_session_duration(self):
        events = [_event("2026-10-28T12:00:00+00:00", "session_start", "s1")]
        sessions = [_session("s1", "2026-10-28T12:00:00+00:00",
                             ended="2026-10-28T12:20:00+00:00")]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg(), sessions)
        assert stats["study_minutes"] == 20.0

    def test_active_session_counts_to_last_event(self):
        events = [_event("2026-10-28T12:00:00+00:00", "session_start", "s1")]
        sessions = [_session("s1", "2026-10-28T12:00:00+00:00",
                             last_event="2026-10-28T12:05:00+00:00")]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg(), sessions)
        assert stats["study_minutes"] == 5.0

    def test_session_without_start_event_not_counted(self):
        # source 过滤：session_start 事件不在本次事件集里的会话不计入
        events = [_event("2026-10-28T12:00:00+00:00", "search")]
        sessions = [_session("s1", "2026-10-28T12:00:00+00:00",
                             ended="2026-10-28T12:20:00+00:00")]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg(), sessions)
        assert stats["study_minutes"] == 0.0

    def test_multiple_sessions_summed(self):
        events = [
            _event("2026-10-28T10:00:00+00:00", "session_start", "s1"),
            _event("2026-10-28T14:00:00+00:00", "session_start", "s2"),
        ]
        sessions = [
            _session("s1", "2026-10-28T10:00:00+00:00",
                     ended="2026-10-28T10:10:00+00:00"),
            _session("s2", "2026-10-28T14:00:00+00:00",
                     ended="2026-10-28T14:30:00+00:00"),
        ]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg(), sessions)
        assert stats["study_minutes"] == 40.0
        assert stats["session_count"] == 2

    def test_datetimes_accepted_as_well_as_iso(self):
        events = [_event("2026-10-28T12:00:00+00:00", "session_start", "s1")]
        sessions = [{
            "session_id": "s1",
            "started_at": datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc),
            "last_event_at": datetime(2026, 10, 28, 12, 9, tzinfo=timezone.utc),
            "ended_at": None,
        }]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg(), sessions)
        assert stats["study_minutes"] == 9.0

    def test_no_sessions_zero_study_time(self):
        # 检索/导入事件不再产生估算时长
        events = [
            _event("2026-10-28T12:00:00+00:00"),
            _event("2026-10-28T12:10:00+00:00"),
            _event("2026-10-28T12:20:00+00:00"),
        ]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg())
        assert stats["study_minutes"] == 0.0


class TestCounts:
    def test_event_type_counts_and_sessions(self):
        events = [
            _event("2026-10-28T12:00:00+00:00", "search", "s1"),
            _event("2026-10-28T12:05:00+00:00", "search", "s1"),
            _event("2026-10-28T13:00:00+00:00", "analyze", "s2"),
            _event("2026-10-28T14:00:00+00:00", "quiz"),
            _event("2026-10-28T15:00:00+00:00", "answer", "s3"),
        ]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg())
        assert stats["search_count"] == 2
        assert stats["analyze_count"] == 1
        # M3 的答题事件（answer）和旧 quiz 事件都计入答题次数
        assert stats["quiz_count"] == 2
        assert stats["total_events"] == 5

    def test_session_start_events_count_sessions(self):
        events = [
            _event("2026-10-28T12:00:00+00:00", "session_start", "s1"),
            _event("2026-10-28T12:01:00+00:00", "question", "s1"),
            _event("2026-10-28T12:02:00+00:00", "answer", "s1"),
        ]
        stats = compute_usage_stats(events, ZoneInfo("UTC"), _cfg())
        assert stats["session_count"] == 1
        assert stats["quiz_count"] == 1
