# RAG Design — Brasaland Knowledge Base (Milestone 7)

An assistant that answers location-manager and customer-facing questions
("how many points for Gold tier?", "does the BBQ Ribs have allergens?")
the way a trained salesperson would — confidently, from the official
manuals, never inventing a number that isn't written down anywhere.

## 1. End-to-end flow

```
docs/company-knowledge-base/*.md
        │  read by setup()
        ▼
  chunk_document()            data/process/rag.py
        │  one dict per chunk: {section, text}
        ▼
     embed()                  data/process/embeddings.py
        │  text -> vector (same function used again at query time)
        ▼
  Qdrant upsert                "brasaland_knowledge" collection
        (setup() ends here — indexing is offline, run once per change
         to the source docs)

═══════════════════════════ query time ═══════════════════════════

  user question
        │
        ▼
   retrieve(question)         data/pipelines/rag.py
        │  embed() the question -> Qdrant query_points() -> top-k
        │  chunks scoring >= min_score
        ▼
  generate_answer(question, context)
        │  prompt = salesperson voice + only the retrieved chunks
        │  -> generation LLM -> answer string
        │  (empty context short-circuits to a fixed "not enough
        │   information" message -- the LLM is never called)
        ▼
  query(question) = retrieve() + generate_answer(), nothing else
        │
        ▼
  POST /knowledge/query        services/api/routes/knowledge.py
        │  { "answer": "..." } only -- no chunks, no scores
        ▼
  Knowledge Base Assistant page   uis/backoffice
```

`setup()`, `embed()`, `retrieve()`, `query()`, and the generation call are
five separate functions on purpose (per the ticket): a later project (the
LangGraph agent) can call `retrieve()` and `generate_answer()` directly as
two steps, without going through `query()`'s wrapping or re-indexing
anything.

## 2. Chunking strategy

Implemented in `chunk_document()` in `data/process/rag.py`.

Each source doc is first split on **blank lines** into blocks — this
naturally separates the title, intro paragraphs, single-sentence rules
("Minimum stock rule: ...") and header+list groups from each other,
because Markdown already puts a blank line between them but *not* between
a list's own items.

A block is then split further, **one chunk per list item**, only when
both are true:
- it's a **dash list** (`- item`), not a numbered list
- it has **3 or more items**

Dash lists in these four docs are always independent facts — one menu
dish's allergens, one loyalty tier, one supplier category, one FAQ
answer. Splitting them means a question about *one* dish or *one* tier
retrieves a chunk about that thing alone, not a chunk padded with five
unrelated dishes.

Numbered lists (`1. 2. 3.`) are never split this way. In this corpus
every numbered list is an ordered **procedure** — the daily waste-logging
steps, the allergy protocol — where step 2 only makes sense after step 1.
Splitting those would turn a procedure into a random step people
retrieve out of order.

A 2-item dash list (e.g. waste-protocol's "causes accepted without a
note") stays as one chunk too — under the 3-item threshold, there's no
retrieval benefit to splitting two short lines apart.

This produced, from the four current documents:

| Document           | Chunks |
| ------------------- | -----: |
| loyalty-program      |      9 |
| menu-allergens        |      9 |
| supplier-ordering     |      7 |
| waste-protocol         |      5 |

All comfortably above the ticket's 3-chunks-per-document minimum, and no
chunk cuts a sentence, list item, or procedure step in half.

Every chunk's payload keeps `source_document` and `section` (see
`CONTEXT-brasaland.md`'s payload schema) so an answer can always be traced
back to which manual and which part of it it came from, even though the
API response itself never shows that to the caller.

## 3. Embedding practices

- **Model:** `pplx-embed-v1-0.6b`, via 4Geeks' own LiteLLM gateway
  (`EMBEDDING_PROVIDER=openai`, base URL `https://llm.4geeks.ai`, model ID
  `downtown-miami/openrouter/perplexity/pplx-embed-v1-0.6b` —
  `data/process/embeddings.py`). 1024-dimension vectors, measured directly
  against the endpoint rather than assumed. `embed()` is the single
  function called both by `setup()` at index time (for chunks) and by
  `retrieve()` at query time (for the user's question), so both sides are
  guaranteed to land in the same vector space.
- **Local fallback:** `data/process/embeddings.py` still defaults to
  `BAAI/bge-small-en-v1.5` via `fastembed` (local, free, no API key) when
  `EMBEDDING_PROVIDER` is unset — keeps the module (and the test suite)
  importable with zero setup. `.env` overrides this to the gateway above
  for real indexing/querying.
- **Distance metric:** cosine (`Distance.COSINE` in `setup()`'s
  `recreate_collection` call) — the standard choice for sentence-embedding
  models; re-check this against pplx-embed-v1-0.6b's own docs if Recall@3
  (section 4) comes out surprisingly low, since not every embedding model
  is meant to be compared this way.
- **Generation model is a separate model ID from embeddings**, per the
  ticket's "never reuse the generation model for embeddings": generation
  uses the same gateway's `downtown-miami/groq/llama-3.1-8b-instant`
  (`data/pipelines/generation_client.py`), not the embeddings model.

## 4. Retrieval threshold (`min_score`)

**Measured** (not a starting guess): **0.27** (`DEFAULT_MIN_SCORE` in
`data/pipelines/rag.py`), `k=5`.

Ran all 10 questions in `data/eval/test-queries.json` through `retrieve()`
with `min_score=0.0` (i.e. no filtering) and looked at every returned
score:

- **Recall@3: 10/10** — every question's top-3 results included a chunk
  from its expected document.
- Every **correct**-document hit, across all 10 questions, scored
  **0.285 or higher**.
- The only two **wrong**-document hits that showed up anywhere in the
  entire run (Q7 and Q8's 5th-place result each) both scored exactly
  **0.254**.

That's a real, if narrow, gap between 0.254 (highest false positive) and
0.285 (lowest true positive) — 0.27 sits in the middle of it, with about
equal margin on both sides. It's a slightly stricter cut than an
un-measured `0.3` placeholder would have been, without losing any
recall: nothing relevant ever scored below 0.285 in this eval, so nothing
correct gets filtered by 0.27, while both known false positives do.

Caveat: this is measured against 10 questions phrased close to how the
docs themselves are worded. A real user asking something more loosely
phrased could still land in an untested part of the score range — worth
revisiting if `/knowledge/query` starts returning "not enough
information" for things that are actually in the knowledge base.

## 5. Faithfulness (never inventing a fact)

Two things enforce this, not just the prompt:
1. `generate_answer()` returns a **fixed message** (`NO_INFO_MESSAGE`)
   without ever calling the LLM when `retrieve()` comes back empty —
   there is structurally nothing for the model to invent from in that
   path.
2. When there *is* context, the prompt instructs the model to answer
   **only** from the given chunks, to never assert "zero risk" (the
   literal wording `brasaland-menu-allergens.en.md` requires), and to say
   plainly when the context doesn't fully answer the question.

## 6. What still needs to happen (see the chat reply for full commands)

- `setup()` has been run against the real Qdrant instance: **30 chunks**
  indexed into `brasaland_knowledge` (9 loyalty-program, 9 menu-allergens,
  7 supplier-ordering, 5 waste-protocol).
- Eval run, Recall@3 and `min_score` finalized — see section 4.
- Remaining: `docker-compose.yml`, `main.py` router wiring, and the
  `uis/backoffice` frontend wiring (see chat for exact edits), then the
  full-stack manual check and PR.