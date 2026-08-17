"""
routes/incidents.py -- Centralized Incident Manager endpoints.

Same pattern as routes/suppliers.py: TinyDB with doc_id as the record's
`id`, and a router-level get_current_user dependency so every route here
needs a valid token.

One deliberate difference from suppliers.py: request bodies are accepted
as a raw dict and validated manually (_validate_or_400) instead of typing
the parameter directly as the Pydantic model. FastAPI's automatic body
validation returns 422 with its own error shape -- the brief for this
project specifically requires 400 with a JSON object naming the bad
field, so validation is done by hand here to get exactly that.

Route ordering note: GET /summary is declared before GET /{incident_id:int}
so "summary" is never mistaken for an id. The `:int` converter on the two
id-based routes is what actually makes that safe -- it's also what stops
"analyze" (from the older app/incidents/routes.py, which shares this same
/api/incidents prefix) from ever being mistaken for an incident id.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import ValidationError
from tinydb import Query as TinyDBQuery

from database import incidents_table
from dependencies import get_current_user
from incident_models import (
    Branch,
    Incident,
    IncidentCategory,
    IncidentCreate,
    IncidentOrigin,
    IncidentStatus,
    IncidentStatusUpdate,
    VALID_STATUS_TRANSITIONS,
)

router = APIRouter(prefix="/api/incidents", tags=["incident-manager"], dependencies=[Depends(get_current_user)])

IncidentField = TinyDBQuery()


def _validate_or_400(model_cls, payload: dict):
    """
    Validate `payload` against a Pydantic model by hand, so a bad request
    gets a 400 with a plain-language, field-specific message -- not
    FastAPI's default 422.
    """
    try:
        return model_cls(**payload)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        field = ".".join(str(part) for part in first_error["loc"]) or "body"
        raise HTTPException(
            status_code=400,
            detail={"field": field, "message": first_error["msg"]},
        )


def _doc_to_incident(doc) -> Incident:
    """Turn a raw TinyDB document into a validated Incident response.

    Any internal-only keys on the document (like source_ref, added by
    scripts/seed_incidents.py for its own duplicate check) are simply
    ignored here -- Incident doesn't declare them, so they never reach
    the client.
    """
    data = dict(doc)
    data["id"] = doc.doc_id
    return Incident(**data)


def _get_doc_or_404(incident_id: int):
    doc = incidents_table.get(doc_id=incident_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return doc


# ---------------------------------------------------------------------------
# POST /api/incidents -- register a new incident. Always starts "open" --
# that's not something the client gets to choose.
# ---------------------------------------------------------------------------

@router.post("", response_model=Incident, status_code=201)
def create_incident(payload: dict = Body(...)):
    data = _validate_or_400(IncidentCreate, payload)

    now = datetime.now(timezone.utc)
    record = data.model_dump(mode="json")
    record["status"] = IncidentStatus.OPEN.value
    record["created_at"] = now.isoformat()
    record["updated_at"] = now.isoformat()

    doc_id = incidents_table.insert(record)
    return _doc_to_incident(incidents_table.get(doc_id=doc_id))


# ---------------------------------------------------------------------------
# GET /api/incidents -- list incidents, optionally filtered. An unknown
# filter value (e.g. a typo) just matches nothing rather than erroring --
# this is a read endpoint, so it fails soft, same as an empty database.
# ---------------------------------------------------------------------------

@router.get("", response_model=list[Incident])
def list_incidents(
    status: str | None = Query(None),
    origin: str | None = Query(None),
    branch: str | None = Query(None),
    category: str | None = Query(None),
):
    conditions = []
    if status is not None:
        conditions.append(IncidentField.status == status)
    if origin is not None:
        conditions.append(IncidentField.origin == origin)
    if branch is not None:
        conditions.append(IncidentField.branch == branch)
    if category is not None:
        conditions.append(IncidentField.category == category)

    if not conditions:
        docs = incidents_table.all()
    else:
        combined_query = conditions[0]
        for extra_condition in conditions[1:]:
            combined_query = combined_query & extra_condition
        docs = incidents_table.search(combined_query)

    docs = sorted(docs, key=lambda d: d.get("created_at", ""), reverse=True)
    return [_doc_to_incident(doc) for doc in docs]


# ---------------------------------------------------------------------------
# GET /api/incidents/summary -- aggregate totals. Every status/category/
# origin/branch value is always present in the response (starting at 0),
# so an empty database returns a complete zero-valued structure instead
# of an empty object.
# ---------------------------------------------------------------------------

@router.get("/summary")
def get_summary():
    docs = incidents_table.all()

    by_status = {s.value: 0 for s in IncidentStatus}
    by_category = {c.value: 0 for c in IncidentCategory}
    by_origin = {o.value: 0 for o in IncidentOrigin}
    by_branch = {b.value: 0 for b in Branch}

    for doc in docs:
        by_status[doc["status"]] = by_status.get(doc["status"], 0) + 1
        by_category[doc["category"]] = by_category.get(doc["category"], 0) + 1
        by_origin[doc["origin"]] = by_origin.get(doc["origin"], 0) + 1
        by_branch[doc["branch"]] = by_branch.get(doc["branch"], 0) + 1

    return {
        "total": len(docs),
        "by_status": by_status,
        "by_category": by_category,
        "by_origin": by_origin,
        "by_branch": by_branch,
    }


# ---------------------------------------------------------------------------
# GET /api/incidents/{id} -- a single incident, 404 if it doesn't exist.
# ---------------------------------------------------------------------------

@router.get("/{incident_id:int}", response_model=Incident)
def get_incident(incident_id: int):
    doc = _get_doc_or_404(incident_id)
    return _doc_to_incident(doc)


# ---------------------------------------------------------------------------
# PATCH /api/incidents/{id}/status -- move an incident through its
# lifecycle. Only transitions listed in VALID_STATUS_TRANSITIONS are
# allowed; anything else (including "no-op" same-status updates) is a 400.
# ---------------------------------------------------------------------------

@router.patch("/{incident_id:int}/status", response_model=Incident)
def update_incident_status(incident_id: int, payload: dict = Body(...)):
    doc = _get_doc_or_404(incident_id)
    data = _validate_or_400(IncidentStatusUpdate, payload)

    current_status = IncidentStatus(doc["status"])
    new_status = data.status
    allowed_next = VALID_STATUS_TRANSITIONS.get(current_status, set())

    if new_status not in allowed_next:
        raise HTTPException(
            status_code=400,
            detail={
                "field": "status",
                "message": f"Cannot move an incident from '{current_status.value}' to '{new_status.value}'.",
            },
        )

    incidents_table.update(
        {
            "status": new_status.value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        doc_ids=[incident_id],
    )
    return _doc_to_incident(incidents_table.get(doc_id=incident_id))
