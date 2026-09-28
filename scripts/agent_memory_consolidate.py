"""
scripts/agent_memory_consolidate.py -- run the agent-memory cleanup now.

The same cleanup already runs automatically after every saved fact (for that
one location). This script runs it for EVERYTHING, so memory stays tidy even if
nobody has saved anything in a while -- the same idea as scripts/nightly_export.py:
run it from cron, or by hand.

What it does (numbers are in services/api/agent/memory/policy.py):
  - drops memory proposals nobody answered within 10 minutes (and logs them)
  - forgets known incidents not seen again in 90 days
  - flags hours/suppliers/preferences not re-confirmed in 180 days as "may be outdated"
  - keeps at most 40 facts per location
Every removal is written to the audit log.

Run from the repo root (Redis must be running):
    cd services/api && uv run python ../../scripts/agent_memory_consolidate.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICES_API_DIR = REPO_ROOT / "services" / "api"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(SERVICES_API_DIR / ".env")

from agent.memory.store import get_store  # noqa: E402


def main() -> None:
    summary = get_store().consolidate()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
