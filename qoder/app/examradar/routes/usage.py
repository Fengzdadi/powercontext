"""Usage records API endpoints."""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..seekdb import get_usage_stats, get_usage_events

router = APIRouter()


@router.get("/api/usage/stats")
def usage_stats(
    course_id: str = Query(...),
    source: str = Query("real"),
    tz_offset_minutes: int = Query(0),
):
    return get_usage_stats(course_id, source, tz_offset_minutes)


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
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=usage_{course_id}_{source}.csv"},
    )
