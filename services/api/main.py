"""
main.py -- FastAPI application entry point for the Brasaland API.

This is now the ONE entry point for the whole backend -- suppliers,
incidents, and users/auth/profiles all live under this single app.
Run it with:
    uvicorn main:app --reload

(There used to be a second app at app/main.py for the incidents
feature alone -- that file is retired. Always use the command above
from here on.)
"""

from contextlib import asynccontextmanager

# Must run before any of our own modules are imported: security.py reads
# JWT_SECRET_KEY and ACCESS_TOKEN_EXPIRE_MINUTES from the environment the
# moment it's imported, so .env has to be loaded first.
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.incidents.routes import router as incidents_analyzer_router
from routes.auth import router as auth_router
from routes.incidents import router as incidents_router
from routes.profiles import router as profiles_router
from routes.suppliers import router as suppliers_router
from routes.users import router as users_router
from seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once on startup. seed_database() only touches the suppliers
    # table and is safe to call every time -- it skips itself if that
    # table already has data.
    seed_database()
    yield


app = FastAPI(
    title="Brasaland API",
    description="Single source of truth for Brasaland's suppliers, after-sales incidents, and user accounts.",
    version="0.2.0",
    lifespan=lifespan,
)

# Lets the frontend (a different port, in Codespaces or localhost) call
# this API during local development. allow_origin_regex covers Codespaces'
# *.app.github.dev preview URLs specifically -- carried over from the old
# incidents app, which needed it to fix a real CORS bug.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"https://.*\.app\.github\.dev",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)
app.include_router(auth_router)
app.include_router(profiles_router)
app.include_router(suppliers_router)
# The analyzer router (CSV upload/export, literal paths like /analyze and
# /results/export) is included before the management router (which has
# /{incident_id:int} on the same /api/incidents prefix). The :int
# converter on that dynamic route already makes the order safe either
# way, but keeping literal paths first is the clearer convention.
app.include_router(incidents_analyzer_router)
app.include_router(incidents_router)


@app.get("/")
def root():
    return {"message": "Brasaland API is running"}