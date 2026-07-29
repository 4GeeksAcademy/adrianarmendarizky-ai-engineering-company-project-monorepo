# Project Brief — Brasaland Digital

## The company

Brasaland is a grilled-food restaurant chain founded in 2008 in Medellín, Colombia. Over fifteen years it has grown to 14 company-owned locations across two countries — Colombia and the United States (Florida) — employing roughly 115 people and generating around USD 6M in annual revenue.

The brand stands for three things: consistent food quality across every location, a warm and consistent service experience, and speed of service. These commitments built the business and are also what make running a two-country operation difficult without proper tooling.

## Who runs it

Led by CEO **Mariana Restrepo** (daughter of the founder, CEO since 2019), who brought the business to the US and now drives its internal-systems build-out. Key functions: Restaurant Operations (Felipe Guerrero), Procurement (Lucía Fernández), Marketing & Digital Experience (Camila Ospina), People & Culture (Ashley Turner, Miami), Training & Quality (Jake Morrison, Miami), and Technology (CTO Nicolás Park, Medellín).

## The problem this project solves

Brasaland is profitable but runs a 14-location, two-country operation on tools built for a single local restaurant: ingredient orders by WhatsApp with no inventory data, a stamp-card loyalty programme that generates no data, no real-time visibility into any location, and leadership decisions made from Tuesday PDF reports and phone calls. Competitors are pulling ahead with digital ordering, data-driven marketing, and operational dashboards.

**Brasaland Digital** is the internal team (this project) chartered to build the tools, systems, and automations that let Brasaland operate like a modern company without losing what makes it good. We are part of that team.

## What we are building (across milestones)

A cohesive internal platform, assembled milestone by milestone:

- A **public corporate website** and candidate-facing entry point.
- A **TypeScript business-logic layer** for restaurant operations analytics (sales, margins, waste, location performance scoring, financial calculations in COP and USD).
- **Internal tooling** (talent pipeline tracker, back-office dashboards) that consumes shared logic and APIs.
- The **infrastructure** (this milestone) that turns these separate deliverables into a coherent, maintainable, AI-ready monorepo.

## Core constraints

- Two countries, two currencies (COP and USD), two labour markets — multi-market correctness is non-negotiable.
- Consistency and trust in the numbers: operational decisions depend on them.
- Modernize without losing the brand's warmth and identity.
