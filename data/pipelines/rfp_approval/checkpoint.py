"""
checkpoint.py -- where the approval graphs save their state (Milestone 9, Part 3).

A SQLite file next to the API code, opened once per process, the same way the
support agent opens agent_checkpoints.db. It is a real file, not memory: a
paused approval survives a server restart and resumes exactly where it stopped.
Set RFP_CHECKPOINT_DB to use another file (the tests do).
"""

import os
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = REPO_ROOT / "services" / "api" / "rfp_checkpoints.db"

_process_checkpointer = None


def make_checkpointer(path=None) -> SqliteSaver:
    """Open a checkpoint file. check_same_thread=False because the API serves
    requests from several threads; SqliteSaver locks around every write."""
    target = str(path or os.environ.get("RFP_CHECKPOINT_DB") or DEFAULT_DB)
    return SqliteSaver(sqlite3.connect(target, check_same_thread=False))


def get_checkpointer() -> SqliteSaver:
    """The one checkpointer for this process."""
    global _process_checkpointer
    if _process_checkpointer is None:
        _process_checkpointer = make_checkpointer()
    return _process_checkpointer
