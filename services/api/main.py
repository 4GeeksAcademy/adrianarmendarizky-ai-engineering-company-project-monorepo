"""
main.py -- FastAPI application entry point for the Brasaland Supplier
Directory API.

This wires everything together:
  - loads the seed data on startup, so the demo never starts from an
    empty database (per the tech lead's note in the brief)
  - registers all of the /suppliers routes
  - allows the frontend (running on a different port) to call this API
    during local development
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.suppliers import router as suppliers_router
from seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once, right when the app starts up, before it accepts any
    # requests. seed_database() is safe to call every time -- it skips
    # itself if the table already has data.
    seed_database()
    yield


app = FastAPI(
    title="Brasaland Supplier Directory API",
    description="Single source of truth for Brasaland's supplier data, replacing the shared spreadsheet.",
    version="0.1.0",
    lifespan=lifespan,
)

# Lets the frontend (a different port in Codespaces / localhost) call
# this API. Fine for local development; a real deployment would list
# specific allowed origins instead of "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(suppliers_router)


@app.get("/")
def root():
    return {"message": "Brasaland Supplier Directory API is running"}