# Backend Architecture Proposal — Brasaland API

**Author:** Adrian Armendariz
**For:** Nicolás Park (CTO) and the Brasaland Digital team
**Status:** Proposal only — no code yet.

---

## 1. What This Document Is For

Before the team starts building the backend, this document explains how we plan to organize the code. The goal is to agree on a simple, clear structure so everyone writes code the same way from the start.

Brasaland needs one API that different parts of the business can use: restaurant sales, menus, suppliers, customers/loyalty, and staff (HR). Right now this data is scattered across spreadsheets, WhatsApp, and paper. The API's job is to bring it all into one place.

---

## 2. Chosen Pattern: Modular Monolith, with MVC Inside Each Module

We're building **one single app** (a "monolith" — not several small separate apps), but organized internally into **modules**, one per business area: `locations`, `sales`, `menus`, `suppliers`, `customers`, `employees`. This is called a **modular monolith**.

Inside each module, we still use **MVC**, the same pattern from class:

- **Model** — the data itself (e.g., what a `Sale` or `Employee` looks like in the database).
- **View** — what the API sends back as a response, using a Pydantic schema.
- **Controller** — the logic that connects the two: reads the request, works with the model, returns the view.

So MVC doesn't go away — it's just applied module by module, instead of one shared `models/`, `schemas/`, `controllers/` folder for the whole app.

**Why this fits Brasaland:** the business is naturally split into separate areas — a sale is not a supplier, a supplier is not an employee — and each area (Operations, Procurement, Marketing, HR) will likely be worked on somewhat independently by different people over time. Grouping by module keeps each area's code together and easy to find, while MVC inside each one keeps that code organized in a way we already know how to write.

**Why not full microservices** (a separate small app per business area, each deployed on its own)? That's the next step up from this, and it's common at larger companies, but it adds real extra work — separate deployments, separate databases, apps having to call each other over the network. Brasaland's team is small and just starting to build its first real backend, so one app with clear internal modules gets everything running sooner, without giving up the ability to split a module out into its own service later if it ever needs to.

---

## 3. Folder Structure

```
backend/
├── app/
│   ├── main.py                # starts the app, connects every module's routes
│   ├── core/
│   │   ├── config.py            # settings loaded from the .env file
│   │   └── database.py          # database connection, shared by all modules
│   ├── locations/
│   │   ├── model.py             # Location table
│   │   ├── schema.py            # what a Location looks like in a response (the "View")
│   │   ├── controller.py        # logic for locations
│   │   └── routes.py            # /locations endpoints
│   ├── sales/
│   │   ├── model.py
│   │   ├── schema.py
│   │   ├── controller.py
│   │   └── routes.py
│   ├── menus/
│   │   └── ...                  # same four files
│   ├── suppliers/
│   │   └── ...
│   ├── customers/               # loyalty accounts, order history
│   │   └── ...
│   └── employees/
│       └── ...
├── .env.example
└── requirements.txt
```

Each module is self-contained: if you're working on sales, everything you need — the model, the schema, the logic, the routes — is inside `app/sales/`. `core/` is the only shared piece, since every module needs a database connection.

**One rule that makes this actually work:** a module shouldn't reach directly into another module's model. For example, if `employees` needs a location's name, it should go through the `locations` module's controller — not read the `Location` model directly. This keeps each module independent, the same way each module has its own model/schema/controller/routes.

---

## 4. Routes (Endpoints)

Each module owns its own routes, instead of putting everything in one file:

- `/locations` — the 14 restaurants (Colombia and Florida)
- `/sales` — daily sales per location, used by the operations dashboard and the executive dashboard
- `/menus` — menu items and pricing
- `/suppliers` — the ~20 suppliers and their pricing
- `/customers` — loyalty accounts and order history (replacing the paper stamp cards)
- `/employees` — staff records, tied to HR needs

`main.py`'s only job is to connect each module's routes to the app — it doesn't contain any business logic itself.

---

## 5. How the Frontend and Backend Work Together

The backend (FastAPI) and the frontend apps (the company website and the internal dashboard) are separate programs. They don't share code directly — the frontend talks to the backend the same way any app talks to any API: by sending HTTP requests (like a GET request to `/sales`) and getting JSON back.

A few basic things this requires:

- The frontend needs to know the backend's address (its URL). We store this in an **environment variable** (`.env` file) instead of typing it directly into the code, so it's easy to change between our local computers and the real server later.
- Because the frontend and backend are separate applications, the backend needs to explicitly allow the frontend to talk to it. This is done with **CORS** settings in FastAPI — without it, the browser blocks the request.

---

## 6. Basic Tech Choices

- **FastAPI** — the framework we're using in class.
- **Python** — the language for the backend.
- **Pydantic** (built into FastAPI) — used for the schemas, to check that data coming in and out has the right shape (e.g., a sale amount is a number, not text).

---

## 7. Risks / Things to Watch Out For

1. **If modules stop staying independent, we lose the whole point of splitting by module.** If the `sales` module starts reading the `employees` model directly (or vice versa), the code turns back into one tangled mess — just spread across folders instead of one big file. The rule from Section 3 (go through the other module's controller, not its model) is what prevents this.

2. **If the frontend ever imports backend code directly instead of calling the API, things get confusing fast.** The rule has to stay simple: frontend and backend only talk through HTTP requests, never by sharing code files. Otherwise it becomes unclear which app "owns" a piece of logic, and bugs get harder to track down.