"""
main.py — starts the Brasaland Incidents API and wires up its routes.

Run from inside services/api/ with:
    uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.incidents.routes import router as incidents_router

app = FastAPI(title="Brasaland Incidents API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_origin_regex=r"https://.*\.app\.github\.dev",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incidents_router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "brasaland-incidents-api"}