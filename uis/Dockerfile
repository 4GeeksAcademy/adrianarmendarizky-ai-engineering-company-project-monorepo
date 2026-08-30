FROM node:22-alpine

# Build context for this Dockerfile is the REPOSITORY ROOT (see
# docker-compose.yml), not ./uis -- necessary because backoffice's
# dashboard page (app/(protected)/page.tsx) imports directly from the
# monorepo's root-level src/ (Milestone 2's sample data/business logic),
# using relative paths like "../../../../src/types/models". Its own
# next.config.ts sets turbopack.root to two levels above the backoffice
# folder specifically so those paths resolve to the monorepo root.
#
# WORKDIR mirrors the real repo layout (uis/website, uis/backoffice,
# and src/ as siblings) so that assumption holds inside the container
# too, with zero changes to the application code.
WORKDIR /workspace/uis

# Dependencies installed separately per app, per the brief -- also lets
# Docker cache each app's install independently.
COPY uis/website/package.json uis/website/package-lock.json ./website/
RUN npm --prefix website install

COPY uis/backoffice/package.json uis/backoffice/package-lock.json ./backoffice/
RUN npm --prefix backoffice install

# Baseline source copy so the image is runnable standalone. The bind
# mounts in docker-compose.yml take over at runtime -- see the
# node_modules/.next anonymous-volume notes there for why that's safe.
COPY uis/website ./website
COPY uis/backoffice ./backoffice

# The sibling src/ directory backoffice's dashboard page needs --
# placed at /workspace/src, matching its real position one level above
# uis/ in the actual repo.
COPY src /workspace/src

COPY uis/start.sh ./start.sh
RUN chmod +x ./start.sh

EXPOSE 3000 3001

CMD ["./start.sh"]
