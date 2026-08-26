"""
seed_inventory.py -- one-time seed data for the inventory feature.

Populates Ingredient / IngredientEntry / IngredientExit in Supabase
with the minimum records CONTEXT.md requires, so /inventory has real
data to show during the demo.

Mirrors seed.py's existing pattern: safe to call on every startup,
skips itself once ingredients already exist.
"""

from sqlmodel import Session, select

from database import engine, users_table
from inventory_models import Ingredient, IngredientEntry, IngredientExit


def _seed_user_uuid() -> str | None:
    """Grab any existing TinyDB user's id to attach seeded orders to.

    CONTEXT.md requires every seeded entry/exit to reference a real
    user_uuid, and doc_id is TinyDB's own row id -- exactly what
    get_current_user() converts back into a User elsewhere in the app.
    Returns None if no user has been registered yet (a fresh clone,
    before you've walked through the /docs register flow).
    """
    existing = users_table.all()
    if not existing:
        return None
    return str(existing[0].doc_id)


def seed_inventory() -> None:
    if engine is None:
        # DATABASE_URL isn't set yet -- nothing to seed.
        return

    seed_user_uuid = _seed_user_uuid()
    if seed_user_uuid is None:
        print(
            "No TinyDB users found yet -- skipping inventory seed. "
            "Register a user (POST /users) and restart the app to seed."
        )
        return

    with Session(engine) as session:
        if session.exec(select(Ingredient)).first():
            print("Inventory tables already have data -- skipping seed.")
            return

        ingredients = [
            Ingredient(name="Beef brisket", sku="BRS-BEEF-001", unit="kg", category="meat", country="CO"),
            Ingredient(name="Pork ribs", sku="BRS-PORK-001", unit="kg", category="meat", country="US"),
            Ingredient(name="Chimichurri sauce", sku="BRS-SAUCE-001", unit="litre", category="sauce", country="CO"),
            Ingredient(name="House BBQ sauce", sku="BRS-SAUCE-002", unit="litre", category="sauce", country="US"),
            Ingredient(name="Yuca (cassava)", sku="BRS-PROD-001", unit="kg", category="produce", country="CO"),
            Ingredient(name="Takeaway box (M)", sku="BRS-PKG-001", unit="unit", category="packaging", country="CO"),
        ]
        session.add_all(ingredients)
        session.commit()
        for ingredient in ingredients:
            session.refresh(ingredient)
        by_sku = {i.sku: i for i in ingredients}

        # Minimum 4 entries -- 2 for beef brisket, 1 each for two others.
        entries = [
            IngredientEntry(ingredient_id=by_sku["BRS-BEEF-001"].id, quantity=50, supplier_name="Carnes del Valle S.A.", location_id=1, user_uuid=seed_user_uuid),
            IngredientEntry(ingredient_id=by_sku["BRS-BEEF-001"].id, quantity=30, supplier_name="Carnes del Valle S.A.", location_id=1, user_uuid=seed_user_uuid),
            IngredientEntry(ingredient_id=by_sku["BRS-PORK-001"].id, quantity=40, supplier_name="MiamiMeat Co.", location_id=8, user_uuid=seed_user_uuid),
            IngredientEntry(ingredient_id=by_sku["BRS-SAUCE-001"].id, quantity=20, supplier_name="Salsas Artesanales Ltda.", location_id=1, user_uuid=seed_user_uuid),
        ]
        session.add_all(entries)
        session.commit()

        # Minimum 3 exits, at least one "waste" -- all comfortably below
        # what was just delivered, so nothing here would ever trip the
        # negative-stock rule.
        exits = [
            IngredientExit(ingredient_id=by_sku["BRS-BEEF-001"].id, quantity=25, reason="consumption", location_id=1, user_uuid=seed_user_uuid),
            IngredientExit(ingredient_id=by_sku["BRS-PORK-001"].id, quantity=10, reason="consumption", location_id=8, user_uuid=seed_user_uuid),
            IngredientExit(ingredient_id=by_sku["BRS-SAUCE-001"].id, quantity=3, reason="waste", location_id=1, user_uuid=seed_user_uuid),
        ]
        session.add_all(exits)
        session.commit()

        print(
            f"Seeded {len(ingredients)} ingredients, {len(entries)} entries, "
            f"and {len(exits)} exits into Supabase."
        )