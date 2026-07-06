# Brasaland — Talent Pipeline Tracker

Internal candidate management tool for Brasaland's People & Culture team, built for the Executive Assistant search. It consumes the course's mock recruitment API and lets the team view, filter, search, update, and manage candidates through the hiring pipeline.

Built with **Next.js (App Router)**, **TypeScript**, and **Tailwind CSS**. Component-level state only (React hooks); no external state library.

---

## Requirements

- **Node.js 20+** (the project will not build on older versions)
- npm

---

## Setup

From this app's directory (`uis/talent-pipeline-tracker/`):

```bash
# 1. Install dependencies
npm install

# 2. Create the environment file
cp .env.example .env.local
```

Then open `.env.local` and set the API base URL:

```
NEXT_PUBLIC_API_URL=https://playground.4geeks.com/tracker/api/v1
```

> The variable must be prefixed with `NEXT_PUBLIC_` so the browser can read it.
> `.env.local` is not committed to the repository; `.env.example` documents the required variable.

---

## Running

```bash
npm run dev
```

The app runs at `http://localhost:3000`. In GitHub Codespaces, open the forwarded port from the **Ports** tab if the preview does not appear automatically.

---

## Using the app

### Candidate list (`/`)
- Shows every candidate with name, position, status, and stage.
- **Search** by name or email — filters live as you type, no page reload.
- **Filter** by status and by stage using the dropdowns. Filters and search are stored in the URL, so a filtered view can be shared or bookmarked.
- Click any candidate to open their detail page.
- **Register candidate** (top right) opens the new-candidate form.

### Candidate detail (`/candidates/[id]`)
- Displays all fields: email, phone, years of experience, application date, LinkedIn, and CV links.
- **Update status** and **update stage** using the dropdowns — changes save immediately and show confirmation.
- **Notes:** add an internal note after a call or interview, and delete notes that are no longer needed. Notes are visible only here, in the detail view.
- **Edit** (top right) opens the edit form pre-filled with the candidate's data.

### Register a candidate (`/candidates/new`)
- Form to add a candidate who applied through another channel.
- Required fields are validated before submission, with specific error messages.
- On success, you are taken to the new candidate's detail page.

### Edit a candidate (`/candidates/[id]/edit`)
- Same form, pre-filled, for correcting a candidate's data.
- Saves via the API and returns you to the detail page.

---

## Status and stage labels

The interface always shows human-readable labels, never raw API values.

| Status (API) | Shown as    | | Stage (API)           | Shown as            |
| ------------ | ----------- |-| --------------------- | ------------------- |
| received     | Received    | | pending               | Pending review      |
| in_progress  | In progress | | review                | Under review        |
| selected     | Selected    | | personal_interview    | Personal interview  |
| discarded    | Discarded   | | technical_interview   | Technical interview |
|              |             | | offer_presented       | Offer presented     |

---

## Project structure

```
uis/talent-pipeline-tracker/
├── app/
│   ├── page.tsx                       # Candidate list
│   └── candidates/
│       ├── new/page.tsx               # Register form
│       └── [id]/
│           ├── page.tsx               # Candidate detail
│           └── edit/page.tsx          # Edit form
├── components/                        # Badge, shared form fields
├── lib/                               # Labels, badge tones, validation
├── services/api.ts                    # All API calls
└── types/candidate.ts                 # API data types
```

---

## Notes for evaluation

- All API calls are handled asynchronously with `async/await` and are centralized in `services/api.ts`.
- Every data operation surfaces loading, success, and error states to the user.
- After a create, update, or note change, the UI reflects the change without a full page reload.
- The interface uses Brasaland's framing throughout (Executive Assistant search, Medellín headquarters).