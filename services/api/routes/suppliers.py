"""
routes/suppliers.py -- All supplier directory endpoints.

Each function below handles one endpoint from the brief. TinyDB gives
every inserted record an integer "doc_id" automatically -- that's what
we use as the supplier's `id` in responses, so we never have to manage
IDs ourselves.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from tinydb import Query as TinyDBQuery

from database import suppliers_table
from dependencies import get_current_user
from supplier_models import (
    Category,
    Country,
    Supplier,
    SupplierCreate,
    SupplierRateUpdate,
    SupplierStatusUpdate,
)

# dependencies=[Depends(get_current_user)] applies to every route on this
# router at once -- AUTH-01 requires all of these to need a valid token.
router = APIRouter(prefix="/suppliers", tags=["suppliers"], dependencies=[Depends(get_current_user)])

# A reusable "query builder" for TinyDB -- SupplierField.country == "USA"
# is how TinyDB expresses "find documents where country equals USA".
SupplierField = TinyDBQuery()


def _doc_to_supplier(doc) -> Supplier:
    """Turn a raw TinyDB document into a validated Supplier response,
    adding the document's doc_id as the `id` field."""
    data = dict(doc)
    data["id"] = doc.doc_id
    return Supplier(**data)


def _get_doc_or_404(supplier_id: int):
    doc = suppliers_table.get(doc_id=supplier_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Supplier {supplier_id} not found")
    return doc


# ---------------------------------------------------------------------------
# POST /suppliers -- create a new supplier
# ---------------------------------------------------------------------------

@router.post("", response_model=Supplier, status_code=201)
def create_supplier(supplier: SupplierCreate):
    record = supplier.model_dump(mode="json")
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    doc_id = suppliers_table.insert(record)
    return _doc_to_supplier(suppliers_table.get(doc_id=doc_id))


# ---------------------------------------------------------------------------
# GET /suppliers -- list all suppliers, optionally filtered by country
# and/or category via query params: ?country=USA / ?category=carne
# ---------------------------------------------------------------------------

@router.get("", response_model=list[Supplier])
def list_suppliers(
    country: Country | None = Query(None),
    category: Category | None = Query(None),
):
    if country is None and category is None:
        docs = suppliers_table.all()
    else:
        conditions = []
        if country is not None:
            conditions.append(SupplierField.country == country.value)
        if category is not None:
            # categories is a list on each document, so we check whether
            # the requested category shows up anywhere inside it.
            conditions.append(
                SupplierField.categories.test(lambda cats, c=category.value: c in cats)
            )
        combined_query = conditions[0]
        for extra_condition in conditions[1:]:
            combined_query = combined_query & extra_condition
        docs = suppliers_table.search(combined_query)

    return [_doc_to_supplier(doc) for doc in docs]


# ---------------------------------------------------------------------------
# GET /suppliers/{id} -- a single supplier, 404 if it doesn't exist
# ---------------------------------------------------------------------------

@router.get("/{supplier_id}", response_model=Supplier)
def get_supplier(supplier_id: int):
    doc = _get_doc_or_404(supplier_id)
    return _doc_to_supplier(doc)


# ---------------------------------------------------------------------------
# PATCH /suppliers/{id}/rate -- update the rate, stamp updated_at
# ---------------------------------------------------------------------------

@router.patch("/{supplier_id}/rate", response_model=Supplier)
def update_rate(supplier_id: int, payload: SupplierRateUpdate):
    _get_doc_or_404(supplier_id)
    suppliers_table.update(
        {
            "rate_per_unit": payload.rate_per_unit,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        doc_ids=[supplier_id],
    )
    return _doc_to_supplier(suppliers_table.get(doc_id=supplier_id))


# ---------------------------------------------------------------------------
# PATCH /suppliers/{id}/status -- activate/suspend a supplier.
# An invalid status value never reaches this function: Pydantic
# rejects it with a 422 first, because SupplierStatusUpdate only
# accepts the SupplierStatus enum.
# ---------------------------------------------------------------------------

@router.patch("/{supplier_id}/status", response_model=Supplier)
def update_status(supplier_id: int, payload: SupplierStatusUpdate):
    _get_doc_or_404(supplier_id)
    suppliers_table.update(
        {"status": payload.status.value},
        doc_ids=[supplier_id],
    )
    return _doc_to_supplier(suppliers_table.get(doc_id=supplier_id))


# ---------------------------------------------------------------------------
# DELETE /suppliers/{id} -- for correcting bad data, not routine removal
# (per the brief: suppliers are suspended, not deleted, in normal use)
# ---------------------------------------------------------------------------

@router.delete("/{supplier_id}")
def delete_supplier(supplier_id: int):
    _get_doc_or_404(supplier_id)
    suppliers_table.remove(doc_ids=[supplier_id])
    return {"detail": f"Supplier {supplier_id} deleted"}