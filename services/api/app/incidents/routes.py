"""
incidents/routes.py

HTTP endpoints for the incident analysis feature:
  POST /api/incidents/analyze          — upload a CSV, get the summary back as JSON
  GET  /api/incidents/results/export   — download the last summary as a CSV
"""
import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from dependencies import get_current_user

from . import controller

# dependencies=[Depends(get_current_user)] applies to every route on this
# router at once -- AUTH-01 requires all of these to need a valid token.
router = APIRouter(
    prefix="/api/incidents", tags=["incidents"], dependencies=[Depends(get_current_user)]
)

@router.post("/analyze")
async def analyze_incidents(file: UploadFile = File(...)):
    file_bytes = await file.read()

    try:
        result = controller.run_analysis(file.filename, file_bytes)
    except controller.EmptyFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except controller.InvalidCsvError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return result


@router.get("/results/export")
async def export_results():
    rows = controller.get_last_export_rows()
    if rows is None:
        raise HTTPException(
            status_code=404,
            detail="No analysis has been run yet. Upload a file to /api/incidents/analyze first.",
        )

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["metric", "value", "percentage"])
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=results.csv"},
    )
