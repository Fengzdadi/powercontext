"""Coverage analysis API endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from ..coverage import analyze, get_latest

router = APIRouter()


class AnalyzeRequest(BaseModel):
    course_id: str
    syllabus_text: str


@router.post("/api/coverage/analyze")
def coverage_analyze(req: AnalyzeRequest,
                     x_examradar_source: Optional[str] = Header(None)):
    source = "auto" if x_examradar_source == "auto" else "real"
    try:
        result = analyze(req.course_id, req.syllabus_text, source=source)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/coverage/latest")
def coverage_latest(course_id: str = Query(...)):
    result = get_latest(course_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No coverage analysis found")
    return result
