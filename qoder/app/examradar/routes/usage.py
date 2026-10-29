"""Usage records API endpoints."""
from __future__ import annotations

import csv
import io
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..seekdb import get_usage_stats, get_usage_events

router = APIRouter()


@router.get("/api/usage/stats")
def usage_stats(
    course_id: str = Query(...),
    source: str = Query("real"),
    tz: str = Query("UTC", description="IANA time zone name, e.g. America/New_York"),
):
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=400, detail=f"unknown time zone: {tz}")
    stats = get_usage_stats(course_id, source, tz)
    stats["tz"] = tz
    return stats


@router.get("/api/usage/export")
def usage_export(
    course_id: str = Query(...),
    source: str = Query("real"),
    format: str = Query("csv"),
):
    events = get_usage_events(course_id, source, limit=10000)
    if format == "json":
        return events

    output = io.StringIO()
    # UTF-8 BOM so Excel recognizes the encoding and shows Chinese correctly
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["id", "session_id", "course_id", "source", "event",
                     "payload", "created_at"])
    for e in events:
        writer.writerow([
            e.get("id"), e.get("session_id"), e.get("course_id"),
            e.get("source"), e.get("event"), e.get("payload"),
            e.get("created_at"),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=usage_{course_id}_{source}.csv"},
    )
