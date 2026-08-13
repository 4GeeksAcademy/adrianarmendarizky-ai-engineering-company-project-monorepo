# Backoffice Dashboard, Incident Analysis, and Talent Pipeline Tracker Apps

## How to run / verify
 
Five terminals: the backend, plus one per protected app.
 
```bash
# backend
cd services/api && uv sync && uv run uvicorn main:app --reload
 
# each frontend app, its own terminal
cd uis/backoffice && npm run dev
cd uis/incidents && npm run dev
cd uis/talent-pipeline-tracker && npm run dev
```
 
Each app needs its own `.env.local` with `NEXT_PUBLIC_API_URL` — `services/api`'s address for Backoffice and Incidents, and `https://playground.4geeks.com/tracker/api/v1` specifically for Talent Pipeline Tracker.
 
Verification: visit Incidents or Talent Pipeline Tracker logged out — both should redirect to Backoffice's `/login`. Log in there, and you should land back on whichever app you actually started from, already authenticated, with no manual token copying required. From there: Backoffice's suppliers page and account/profile page, Incidents' upload-and-export flow, and Talent Pipeline Tracker's candidate list should all work normally with a real session, and all three should reject access with none.