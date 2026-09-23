"""
tests/pipelines/test_agent.py -- Part 1 of 2 (LangGraph migration): the
agent evals the ticket asks for.

These are EVALS, not unit tests, and that's deliberate: they run the
real compiled graph end to end -- real embed(), real Qdrant search
against the actual indexed `brasaland_knowledge` collection, real call
to the generation model. Unlike tests/pipelines/test_rag.py (which mocks
every external call so it can run with no live services at all), these
need Qdrant running and a working services/api/.env, the same as running
the app for real -- that's the point: the ticket asks for evals that
assert the agent's actual behavior and trace, not the code path with
canned inputs.

test_rag.py is unaffected by any of this and must still pass on its own
-- these evals are additive, not a replacement.

Run with (from services/api, same as test_rag.py):
    uv run python -m pytest ../../tests/pipelines/test_agent.py -v
"""

import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from agent.graph import get_trace, graph  # noqa: E402
from rag import NO_INFO_MESSAGE  # noqa: E402  (data/pipelines/rag.py, already on sys.path via agent.nodes)

# A question with a real, verifiable answer in the knowledge base.
GROUNDED_QUESTION = "How many points do I need for Gold tier?"
EXPECTED_FACT = "50"  # brasaland-loyalty-program.en.md: "Gold (50+ points)"

# A question nothing in the knowledge base answers.
UNGROUNDED_QUESTION = "What is the CEO's favorite color?"


def _run(question: str) -> tuple[dict, list[dict]]:
    """Runs the graph once under a fresh thread_id and returns
    (result, trace) -- the trace read back from the checkpoint file, not
    from anything held in memory from the run itself."""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke({"question": question}, config)
    return result, get_trace(config)


def test_grounded_question_routes_through_generate():
    """Eval 1 (routing): for a question the knowledge base actually
    answers, the trace must show retrieve running before generate --
    the ticket's own example of a trace-based criterion -- and no_info
    must never run."""
    _, trace = _run(GROUNDED_QUESTION)
    nodes_run = [step["node"] for step in trace]

    assert "retrieve" in nodes_run
    assert "generate" in nodes_run
    assert nodes_run.index("retrieve") < nodes_run.index("generate")
    assert "no_info" not in nodes_run


def test_ungrounded_question_routes_to_no_info_not_generate():
    """Eval 2 (routing): for a question nothing in the knowledge base
    covers, retrieve must still run, but the graph must route to
    no_info -- generate (and therefore the generation LLM) must never
    be called, and the final answer must be the honest NO_INFO_MESSAGE,
    not an invented one."""
    result, trace = _run(UNGROUNDED_QUESTION)
    nodes_run = [step["node"] for step in trace]

    assert "retrieve" in nodes_run
    assert "no_info" in nodes_run
    assert "generate" not in nodes_run
    assert result["answer"] == NO_INFO_MESSAGE


def test_answer_is_grounded_in_the_knowledge_base():
    """Eval 3 (REQUIRED by the ticket): the answer to a known policy
    question must contain the actual fact from the source document --
    trace/routing correctness (evals 1-2 above) is not a substitute for
    this. This is in addition to, not instead of, test_rag.py's own
    retrieve()/generate_answer() unit tests."""
    result, _ = _run(GROUNDED_QUESTION)
    assert EXPECTED_FACT in result["answer"]


def test_trace_is_queryable_after_the_run_from_a_fresh_lookup():
    """Eval 4 (checkpointing/tracing): a trace fetched by thread_id in a
    call completely separate from the one that produced it -- proving
    get_trace() reads real, persisted state from the checkpoint file,
    not something only available immediately after invoke() returns.
    Also confirms compile()'s checkpointer wiring is real: an unrelated
    thread_id must not blend into it."""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke({"question": GROUNDED_QUESTION}, config)

    # A brand-new lookup, independent of the invoke() call above.
    trace_again = get_trace({"configurable": {"thread_id": thread_id}})
    assert [step["node"] for step in trace_again] == [
        "__start__",
        "receive_question",
        "retrieve",
        "generate",
    ]

    # A thread_id that never ran anything has no trace at all.
    assert get_trace({"configurable": {"thread_id": str(uuid.uuid4())}}) == []
