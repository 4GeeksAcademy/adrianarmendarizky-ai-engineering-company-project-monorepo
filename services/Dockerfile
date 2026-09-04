FROM python:3.12-slim

# Build context for this Dockerfile is the REPOSITORY ROOT (see
# docker-compose.yml), not ./services -- necessary because the API
# imports from sibling directories at runtime, not just its own folder.
# All of them use hand-rolled path math that assumes a specific, fixed
# directory depth:
#
#   services/api/app/incidents/controller.py:
#     REPO_ROOT = Path(__file__).resolve().parents[4]
#     (4 levels up: incidents/ -> app/ -> api/ -> services/ -> root)
#     needs REPO_ROOT/scripts and REPO_ROOT/packages/shared on sys.path
#
#   scripts/analyze.py:
#     REPO_ROOT = Path(__file__).resolve().parent.parent
#     (2 levels up: scripts/ -> root) needs REPO_ROOT/packages/shared
#
#   services/api/routes/reporting.py:
#     REPO_ROOT = Path(__file__).resolve().parents[3]
#     (3 levels up: routes/ -> api/ -> services/ -> root)
#     needs REPO_ROOT/data/pipelines on sys.path, to import the flow
#     POST /reporting/pipeline-runs triggers.
#
# WORKDIR mirrors that exact structure so all of these files' own path
# calculations resolve correctly inside the container with zero changes
# to the application code itself.
WORKDIR /workspace/services/api

RUN pip install --no-cache-dir uv

# Dependencies first (cached layer, skipped unless pyproject.toml/uv.lock
# actually change). --no-install-project is necessary specifically
# because uv (unlike pip) also tries to install the local project
# itself, not just its dependencies -- which would fail here since no
# source exists yet at this point.
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-install-project

# The real source, in the four locations the app actually needs:
# services/api itself, plus the three sibling directories from the note
# above. Finishing the sync here installs the project itself in
# editable mode.
COPY services/api /workspace/services/api
COPY scripts /workspace/scripts
COPY packages/shared /workspace/packages/shared
COPY data/pipelines /workspace/data/pipelines
RUN uv sync --frozen

EXPOSE 8000

# --reload-dir on all four bind-mounted paths (see docker-compose.yml) --
# uvicorn's default --reload only watches its own working directory, so
# without this, edits to scripts/, packages/shared/, or data/pipelines/
# on the host wouldn't trigger a reload even though the bind mount
# reflects them immediately on disk inside the container.
CMD ["uv", "run", "uvicorn", "main:app", "--reload", \
     "--reload-dir", "/workspace/services/api", \
     "--reload-dir", "/workspace/scripts", \
     "--reload-dir", "/workspace/packages/shared", \
     "--reload-dir", "/workspace/data/pipelines", \
     "--host", "0.0.0.0", "--port", "8000"]
