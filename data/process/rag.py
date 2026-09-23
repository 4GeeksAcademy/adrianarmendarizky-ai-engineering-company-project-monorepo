"""
data/process/rag.py -- Milestone 7 (RAG & Knowledge Base): data preparation
and indexing.

Two responsibilities live here, per CONTEXT-brasaland.md section "Domain
Data Structure":
  - setup()  reads the source documents from docs/company-knowledge-base/,
             splits them into semantic chunks, embeds each chunk, and
             upserts them into the `brasaland_knowledge` Qdrant collection.
  - embed()  turns one piece of text into a vector. It is the ONLY function
             that calls the embeddings model, and it is used both here (at
             index time, for chunks) and in data/pipelines/rag.py (at query
             time, for the user's question) -- so the two are guaranteed to
             produce vectors in the same space.

Chunking strategy (see docs/rag/rag-design.md for the full writeup):
  Each source doc is first split on blank lines into blocks (title, intro
  paragraphs, "Label: ..." sentences, and header+list groups). A block that
  is a short header followed by a dash ("- ") list of 3+ items is then
  split again, one chunk per list item, because each item is a standalone
  fact (one supplier category, one menu dish, one loyalty tier, one FAQ
  answer) that a salesperson would want retrieved on its own -- bundling
  six dishes into one chunk would bury the one dish someone actually asked
  about. A numbered ("1. 2. 3.") list is never split this way: those are
  ordered procedure steps (e.g. the allergy protocol) that only make sense
  read together, not independent facts.

Run as a script:
    cd services/api && uv run python ../../data/process/rag.py
    cd services/api && uv run python ../../data/process/rag.py --dry-run

Requires QDRANT_URL (and, for the real embeddings model, whatever
EMBEDDING_* variables embeddings.py's provider needs) in services/api/.env.
See embeddings.py in this same folder for how embed() is configured, and
docs/rag/rag-design.md for the model actually used and why.

services/api holds no code this module needs directly, but it is where
.env lives and where this script is run from (see the Run block above) --
same hand-rolled sys.path pattern already used by data/pipelines/pipeline.py
to reach a sibling directory that isn't its own installable package.
"""

import argparse
import os
import re
import sys
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / "services" / "api" / ".env")

from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http.models import Distance, PointStruct, VectorParams  # noqa: E402

from embeddings import embed, EMBEDDING_DIM  # noqa: E402

KNOWLEDGE_BASE_DIR = REPO_ROOT / "docs" / "company-knowledge-base"
QDRANT_COLLECTION = "brasaland_knowledge"  # fixed by CONTEXT-brasaland.md
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
LANGUAGE = "en"

# source_document values used in the payload -- one per file in
# docs/company-knowledge-base/, matching CONTEXT-brasaland.md section 2.
SOURCE_DOCUMENT_BY_FILENAME = {
    "brasaland-loyalty-program.en.md": "loyalty-program",
    "brasaland-waste-protocol.en.md": "waste-protocol",
    "brasaland-menu-allergens.en.md": "menu-allergens",
    "brasaland-supplier-ordering.en.md": "supplier-ordering",
}

# A block gets split one-chunk-per-item only when its list uses this marker
# and has at least this many items. Numbered lists ("1. ", "2. ", ...) are
# procedure steps and are always kept as a single chunk -- see the module
# docstring.
_BULLET_RE = re.compile(r"^- ", re.MULTILINE)
_MIN_ITEMS_TO_SPLIT = 3


def _split_into_blocks(body: str) -> list[str]:
    """Splits markdown body text on blank lines. Each block is either a
    heading, a paragraph, or a "Label:" line immediately followed by its
    list (list items have no blank line between them, so they stay
    attached to their label in the same block)."""
    blocks = re.split(r"\n\s*\n", body.strip())
    return [b.strip() for b in blocks if b.strip()]


def _section_title(block: str) -> str:
    """Best-effort human-readable label for a block, used as the payload
    `section` field. A block that starts with 'Label: rest of sentence'
    (the colon within the first ~80 chars) uses the label; otherwise the
    first sentence, truncated, stands in for a title."""
    flat = re.sub(r"\s+", " ", block).strip()
    first_line = block.splitlines()[0]
    colon_idx = first_line.find(":")
    if 0 < colon_idx <= 80:
        return first_line[:colon_idx].strip()
    first_sentence = re.split(r"(?<=[.!?])\s", flat, maxsplit=1)[0]
    return (first_sentence[:77] + "...") if len(first_sentence) > 80 else first_sentence


def _split_bullet_list_block(block: str) -> list[tuple[str, str]] | None:
    """If `block` is a header/intro line followed by a dash-bulleted list
    of >= _MIN_ITEMS_TO_SPLIT items, returns one (section, chunk_text) pair
    per item, each prefixed with the header so it still reads standalone
    out of context. Returns None if the block doesn't match that shape
    (paragraph, numbered procedure, or a short list not worth splitting)."""
    lines = block.splitlines()
    bullet_start = next((i for i, ln in enumerate(lines) if ln.startswith("- ")), None)
    if bullet_start is None or bullet_start == 0:
        return None  # no header line before the list, or no bullets at all

    header = " ".join(lines[:bullet_start]).strip()
    # Re-join wrapped lines (a continuation line doesn't start with "- ")
    # back onto their bullet before splitting into items.
    items, current = [], None
    for ln in lines[bullet_start:]:
        if ln.startswith("- "):
            if current is not None:
                items.append(current)
            current = ln[2:].strip()
        elif current is not None:
            current += " " + ln.strip()
    if current is not None:
        items.append(current)

    if len(items) < _MIN_ITEMS_TO_SPLIT:
        return None

    return [(header, f"{header} — {item}") for item in items]


def chunk_document(text: str, source_document: str) -> list[dict]:
    """Splits one source document's raw markdown into self-contained
    chunks. Returns a list of {"section": str, "text": str} dicts, in
    document order. Never cuts a sentence, list item, or procedure step in
    half -- see the module docstring for the strategy."""
    lines = text.strip().splitlines()
    title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("#") else None
    body = "\n".join(lines[1:]) if title else text

    chunks: list[dict] = []
    for block in _split_into_blocks(body):
        split = _split_bullet_list_block(block)
        if split:
            for section, chunk_text in split:
                chunks.append({"section": section, "text": chunk_text})
        else:
            section = "Introduction" if not chunks and title else _section_title(block)
            chunks.append({"section": section, "text": block})

    if len(chunks) < 3:
        raise ValueError(
            f"{source_document} produced only {len(chunks)} chunk(s); "
            "the ticket requires at least 3 per document -- check the source file."
        )
    return chunks


def _point_id(source_document: str, chunk_index: int) -> str:
    """Deterministic UUID from (source_document, chunk_index) so re-running
    setup() upserts the same points instead of duplicating them -- this is
    what makes setup() idempotent, per the ticket's Phase 1 checklist."""
    return str(uuid5(NAMESPACE_URL, f"brasaland_knowledge/{source_document}/{chunk_index}"))


def setup(dry_run: bool = False) -> int:
    """Reads every file in docs/company-knowledge-base/, chunks it,
    embeds each chunk with embed(), and upserts all points into the
    `brasaland_knowledge` Qdrant collection (recreating it first, so the
    schema/vector-size always matches EMBEDDING_DIM). Returns the total
    number of chunks indexed. With dry_run=True, chunks and embeds but
    never touches Qdrant -- useful for checking chunk counts/boundaries
    before spending embedding calls."""
    files = sorted(KNOWLEDGE_BASE_DIR.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"No .md files found in {KNOWLEDGE_BASE_DIR}")

    all_points: list[PointStruct] = []
    total_chunks = 0
    for path in files:
        source_document = SOURCE_DOCUMENT_BY_FILENAME.get(path.name, path.stem)
        chunks = chunk_document(path.read_text(encoding="utf-8"), source_document)
        print(f"  {path.name}: {len(chunks)} chunks ({source_document})")
        for i, chunk in enumerate(chunks):
            total_chunks += 1
            if dry_run:
                continue
            vector = embed(chunk["text"])
            all_points.append(
                PointStruct(
                    id=_point_id(source_document, i),
                    vector=vector,
                    payload={
                        "company": "brasaland",
                        "source_document": source_document,
                        "section": chunk["section"],
                        "language": LANGUAGE,
                        "chunk_index": i,
                        "text": chunk["text"],
                    },
                )
            )

    if dry_run:
        return total_chunks

    client = QdrantClient(url=QDRANT_URL)
    # recreate_collection is what keeps setup() idempotent for development:
    # re-running it wipes and rebuilds the collection instead of piling up
    # duplicate or stale points from earlier chunking strategies.
    if client.collection_exists(QDRANT_COLLECTION):
        client.delete_collection(QDRANT_COLLECTION)
    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
    )
    client.upsert(collection_name=QDRANT_COLLECTION, points=all_points)
    return total_chunks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk and embed but don't touch Qdrant -- prints chunk counts per document.",
    )
    args = parser.parse_args()
    n = setup(dry_run=args.dry_run)
    print(f"{'Would index' if args.dry_run else 'Indexed'} {n} chunks into '{QDRANT_COLLECTION}'.")
