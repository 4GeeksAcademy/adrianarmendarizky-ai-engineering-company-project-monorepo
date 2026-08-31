"""
routers/inventory.py -- all /inventory endpoints.

Every write here goes to Supabase (via get_db). Auth still comes from
TinyDB via get_current_user, unchanged -- the two databases don't need
to know about each other, they just both get used by the same routes.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select

from database import get_db
from dependencies import get_current_user
from inventory_models import Ingredient, IngredientEntry, IngredientExit
from inventory_schemas import (
    IngredientCreate,
    IngredientEntryCreate,
    IngredientEntryRead,
    IngredientExitCreate,
    IngredientExitRead,
    IngredientRead,
    InventoryOrderRead,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _current_stock(db: Session, ingredient_id: int) -> float:
    """Stock for ONE ingredient -- fine to call per-ingredient on the
    single-ingredient routes below (get one product, check before an
    outbound write). Not used in list_ingredients -- see the note
    there about why that endpoint calculates stock differently.
    """
    entries = db.exec(
        select(func.sum(IngredientEntry.quantity)).where(
            IngredientEntry.ingredient_id == ingredient_id
        )
    ).one()
    exits = db.exec(
        select(func.sum(IngredientExit.quantity)).where(
            IngredientExit.ingredient_id == ingredient_id
        )
    ).one()
    return (entries or 0) - (exits or 0)


@router.get("/products", response_model=list[IngredientRead])
def list_ingredients(db: Session = Depends(get_db)):
    ingredients = db.exec(select(Ingredient)).all()

    # This is the N+1 trap the brief warns about: calling _current_stock()
    # once per ingredient inside this loop would mean 2 extra queries for
    # every row. Instead, sum entries and exits ONCE each, grouped by
    # ingredient, and look up each ingredient's totals from a dict -- two
    # queries total, no matter how many ingredients there are.
    entry_totals = dict(
        db.exec(
            select(
                IngredientEntry.ingredient_id,
                func.sum(IngredientEntry.quantity),
            ).group_by(IngredientEntry.ingredient_id)
        ).all()
    )
    exit_totals = dict(
        db.exec(
            select(
                IngredientExit.ingredient_id,
                func.sum(IngredientExit.quantity),
            ).group_by(IngredientExit.ingredient_id)
        ).all()
    )

    return [
        IngredientRead(
            **ingredient.dict(),
            current_stock=entry_totals.get(ingredient.id, 0) - exit_totals.get(ingredient.id, 0),
        )
        for ingredient in ingredients
    ]


@router.post("/products", response_model=IngredientRead)
def create_ingredient(
    payload: IngredientCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    ingredient = Ingredient(**payload.dict())
    db.add(ingredient)
    db.commit()
    db.refresh(ingredient)
    # A brand-new ingredient has no entries or exits yet -- stock is 0.
    return IngredientRead(**ingredient.dict(), current_stock=0.0)


@router.get("/products/{ingredient_id}", response_model=IngredientRead)
def get_ingredient(ingredient_id: int, db: Session = Depends(get_db)):
    ingredient = db.get(Ingredient, ingredient_id)
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    return IngredientRead(**ingredient.dict(), current_stock=_current_stock(db, ingredient_id))


@router.post("/orders/inbound", response_model=IngredientEntryRead)
def create_entry(
    payload: IngredientEntryCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    ingredient = db.get(Ingredient, payload.ingredient_id)
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    # Historical average is computed from PRIOR entries only -- query
    # before inserting the new row, so the new entry never averages
    # against itself. Scoped to the same ingredient + supplier, per
    # CONTEXT-brasaland.md ("historical value for that product/supplier").
    # None when there's no prior cost data yet (a brand-new pairing, or
    # every prior entry omitted unit_cost).
    historical_avg_cost = db.exec(
        select(func.avg(IngredientEntry.unit_cost)).where(
            IngredientEntry.ingredient_id == payload.ingredient_id,
            IngredientEntry.supplier_name == payload.supplier_name,
            IngredientEntry.unit_cost.is_not(None),
        )
    ).one()

    entry = IngredientEntry(**payload.dict(), user_uuid=str(current_user.id))
    db.add(entry)
    db.commit()
    db.refresh(entry)
    # Built explicitly from the ORM instance's fields, rather than returning
    # `entry` itself -- response_model=IngredientEntryRead would validate
    # and serialize a raw SQLModel object correctly either way, but the
    # brief is specific that no endpoint should hand back a raw ORM object.
    return IngredientEntryRead(
        **entry.dict(),
        historical_avg_cost=historical_avg_cost,
        product_category=ingredient.category,
        unit=ingredient.unit,
    )


@router.post("/orders/outbound", response_model=IngredientExitRead)
def create_exit(
    payload: IngredientExitCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    ingredient = db.get(Ingredient, payload.ingredient_id)
    if not ingredient:
        raise HTTPException(status_code=404, detail="Ingredient not found")

    # Reject BEFORE writing anything, per the business rule.
    available = _current_stock(db, payload.ingredient_id)
    if payload.quantity > available:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient stock for ingredient '{ingredient.name}'. "
                f"Available: {available}, requested: {payload.quantity}."
            ),
        )

    exit_ = IngredientExit(**payload.dict(), user_uuid=str(current_user.id))
    db.add(exit_)
    db.commit()
    db.refresh(exit_)
    # Same reasoning as create_entry above -- explicit schema, not the raw
    # ORM object. current_stock is recomputed post-write (available - this
    # exit) so the frontend can compare against minimum_stock and decide
    # whether to fire stock_threshold_triggered without a second request.
    return IngredientExitRead(
        **exit_.dict(),
        product_category=ingredient.category,
        unit=ingredient.unit,
        current_stock=available - payload.quantity,
        minimum_stock=ingredient.minimum_stock,
    )


@router.get("/orders", response_model=list[InventoryOrderRead])
def list_orders(db: Session = Depends(get_db)):
    # One query for all ingredients, kept as a dict -- same N+1 avoidance
    # as list_ingredients, since this loop would otherwise do one lookup
    # per entry/exit row to get the ingredient's name and sku.
    ingredients = {i.id: i for i in db.exec(select(Ingredient)).all()}

    orders: list[InventoryOrderRead] = []

    for entry in db.exec(select(IngredientEntry)).all():
        ingredient = ingredients.get(entry.ingredient_id)
        orders.append(
            InventoryOrderRead(
                type="inbound",
                id=entry.id,
                ingredient_id=entry.ingredient_id,
                ingredient_name=ingredient.name if ingredient else "Unknown",
                ingredient_sku=ingredient.sku if ingredient else "Unknown",
                quantity=entry.quantity,
                location_id=entry.location_id,
                created_at=entry.created_at,
                user_uuid=entry.user_uuid,
                supplier_name=entry.supplier_name,
            )
        )

    for exit_ in db.exec(select(IngredientExit)).all():
        ingredient = ingredients.get(exit_.ingredient_id)
        orders.append(
            InventoryOrderRead(
                type="outbound",
                id=exit_.id,
                ingredient_id=exit_.ingredient_id,
                ingredient_name=ingredient.name if ingredient else "Unknown",
                ingredient_sku=ingredient.sku if ingredient else "Unknown",
                quantity=exit_.quantity,
                location_id=exit_.location_id,
                created_at=exit_.created_at,
                user_uuid=exit_.user_uuid,
                reason=exit_.reason,
            )
        )

    orders.sort(key=lambda o: o.created_at)
    return orders