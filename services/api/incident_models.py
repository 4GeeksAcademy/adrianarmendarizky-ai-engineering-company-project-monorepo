"""
incident_models.py -- Pydantic models for the centralized Incident Manager.

Same pattern as models.py (suppliers) and user_models.py: enums restrict
category/status/origin/branch to the fixed sets from CONTEXT.md, and
separate Create/Update/response models control exactly what a client can
send in versus what they get back.

Field names, category codes, branch codes, and status values below are
copied verbatim from CONTEXT-brasaland.en (centralized).md -- don't rename
any of them without checking that file first, since the grading rubric
checks these values exactly.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class IncidentCategory(str, Enum):
    EQUIPMENT_FAILURE = "equipment_failure"
    SUPPLY_ISSUE = "supply_issue"
    CUSTOMER_COMPLAINT = "customer_complaint"
    STAFF_ISSUE = "staff_issue"
    FACILITY_ISSUE = "facility_issue"
    POS_SYSTEM = "pos_system"
    DELIVERY_ISSUE = "delivery_issue"
    OTHER = "other"


class IncidentStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISCARDED = "discarded"


class IncidentOrigin(str, Enum):
    CUSTOMER = "customer"
    BRANCH = "branch"
    INTERNAL = "internal"


class Branch(str, Enum):
    CENTRAL = "central"
    MEDELLIN_CENTRO = "medellin_centro"
    MEDELLIN_LAURELES = "medellin_laureles"
    MEDELLIN_ENVIGADO = "medellin_envigado"
    MEDELLIN_BELLO = "medellin_bello"
    MEDELLIN_ITAGUI = "medellin_itagui"
    BOGOTA_CHAPINERO = "bogota_chapinero"
    BOGOTA_USAQUEN = "bogota_usaquen"
    CALI_GRANADA = "cali_granada"
    BARRANQUILLA_NORTE = "barranquilla_norte"
    MIAMI_DORAL = "miami_doral"
    MIAMI_HIALEAH = "miami_hialeah"
    MIAMI_KENDALL = "miami_kendall"
    ORLANDO_INTERNATIONAL = "orlando_international"
    FORT_LAUDERDALE = "fort_lauderdale"


# Only status changes that are allowed to move *from* the key *to* one of
# the values. An empty set means that status is final. Both
# routes/incidents.py (the live API) and scripts/seed_incidents.py (as a
# sanity check on the historical data) use this same table.
VALID_STATUS_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.OPEN: {IncidentStatus.IN_PROGRESS, IncidentStatus.DISCARDED},
    IncidentStatus.IN_PROGRESS: {IncidentStatus.RESOLVED, IncidentStatus.DISCARDED},
    IncidentStatus.RESOLVED: set(),
    IncidentStatus.DISCARDED: set(),
}


# ---------------------------------------------------------------------------
# IncidentBase -- fields every incident has regardless of how it was
# created. title/description/category/origin/branch are always required;
# CONTEXT is explicit that branch is required for every origin, including
# "internal" incidents with no specific location -- those use "central".
# ---------------------------------------------------------------------------

class IncidentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1)
    category: IncidentCategory
    origin: IncidentOrigin
    branch: Branch


# ---------------------------------------------------------------------------
# IncidentCreate -- body for POST /api/incidents (the registration form).
# Deliberately has no `status` field: a freshly registered incident is
# always "open" -- that's a server-side rule, not something a client
# chooses, so the route sets it rather than trusting client input.
# ---------------------------------------------------------------------------

class IncidentCreate(IncidentBase):
    pass


# ---------------------------------------------------------------------------
# IncidentSeedRecord -- what scripts/seed_incidents.py validates before
# inserting a transformed historical record. Unlike IncidentCreate, this
# *does* include status/created_at/updated_at, because the seed script is
# loading historical facts (some already resolved or discarded, dated in
# the past) rather than registering a brand-new incident through the
# normal flow.
# ---------------------------------------------------------------------------

class IncidentSeedRecord(IncidentBase):
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Incident -- the full record as returned by the API.
# ---------------------------------------------------------------------------

class Incident(IncidentBase):
    id: int
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# IncidentStatusUpdate -- body for PATCH /api/incidents/{id}/status.
# Pydantic guarantees the value is one of the 4 known statuses; whether
# THIS transition is allowed from the incident's CURRENT status is
# checked in the route itself using VALID_STATUS_TRANSITIONS, since that
# depends on the existing record, not just the new value.
# ---------------------------------------------------------------------------

class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus
