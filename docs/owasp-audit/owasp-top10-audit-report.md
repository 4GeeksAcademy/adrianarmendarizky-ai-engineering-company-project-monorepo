# OWASP Top 10 Audit Report: Brasaland

Branch: `feature/owasp-top10-audit`
Date: 2026-10-15
Prepared by: Adrian
Scope: the AI systems inventory in `docs/nist-security/nist-security-report.md` (section 3), plus the backend routes, the four frontends, the MCP server and the Docker setup.
Line numbers are from the code as it was before each fix.

## 1. Summary

- I checked all 10 OWASP categories in three lanes: backend, frontend and agent (section 4).
- I fixed 13 problems (section 3). Each has a before and after result in `docs/owasp-audit/evidence/` (26 files).
- The API test suite now has 83 passing tests: 40 that already existed and 43 new ones.
- The most serious problems were access control: any logged-in user could make themselves an admin or delete any account, and the login hand-off could send a token to any website.
- Open items are in section 5, and the limits of this audit are in section 7.

## 2. Server hardening

This Codespace's own `sshd` (port 2222) is how I connect to it, so I did not change it. I wrote the hardened settings as files in `infra/hardening/` and proved them in a Docker container with its own `sshd`.

Baseline before any change:
- I run as `codespace` (not root), but the user is in the `docker` group and `sudo` works without a password.
- `/etc/ssh/sshd_config` has `PermitRootLogin yes` and `X11Forwarding yes`, and no `AllowUsers` line.
- Ports 2222 (SSH) and 2000 listen on all network interfaces. I could not identify what uses port 2000.

| Requirement | Before | After | Evidence |
| --- | --- | --- | --- |
| No direct SSH root login | `PermitRootLogin yes` | `PermitRootLogin no` | `ssh-before.txt`, `ssh-after.txt` |
| Other SSH rules (key login only, no X11, 3 tries, named users) | 6 FAIL | 6 PASS, and `sshd -T` shows the values the server really uses | `ssh-before.txt`, `ssh-after.txt`, `infra/hardening/check_ssh_config.sh` |
| Non-root user for daily work | `codespace` is not root, but has `sudo` and `docker` | `deploy` user with no password, root password locked (`passwd -S root` prints `L`) | `infra/hardening/Dockerfile` |
| Folder permissions | Not measured | Code and logs: `deploy` only (750). Config: owned by root, `deploy` can read but not change it (750 and 640). Writing to the config folder as `deploy` was refused. | `folder-permissions.txt` |
| Firewall | Not measured | Only ports 22 and 443 accept connections. Redis (6379), Qdrant (6333) and Flower (5555) are blocked. | `firewall-test.txt`, `infra/hardening/firewall.sh` |
| Internal ports in Docker | Redis, Qdrant and Flower were published on all interfaces | Published on `127.0.0.1` only | `ports-before.txt`, `ports-after.txt`, `docker-compose.yml` |

Limits of this part:
- It runs in a demo container, not on a real server.
- I did not try an actual SSH login as root.
- The firewall script covers IPv4 only.
- The API (8000) and the UI (3000, 3001) are still published in `docker-compose.yml`. In production they should sit behind HTTPS, which I did not set up here.
- I could not see any password on Redis, Qdrant or Flower in `docker-compose.yml`. A password could still be set in `.env`, which I did not read.

## 3. Critical fixes with before and after evidence

My rating is my own judgement, not a formal score.

| # | Problem | Category | My rating | Fix | Evidence (before, then after) |
| --- | --- | --- | --- | --- | --- |
| 1 | A logged-in user could make themselves admin (`PUT /users/{id}` with `role`, `services/api/routes/users.py:64-78`) | A01 | Critical | Only an admin can change a role | `users-before.txt` (2 failed, 5 passed), `users-after.txt` (7 passed) |
| 2 | Any logged-in user could delete any account (`services/api/routes/users.py:85-89`) | A01 | Critical | The user themselves or an admin only | same files |
| 3 | Any logged-in user could suspend, delete or change the rate of a supplier (`services/api/routes/suppliers.py:106`, `:126`, `:141`) | A01 | High | Managers and admins only | `suppliers-before.txt` (3 failed, 5 passed), `suppliers-after.txt` (8 passed) |
| 4 | The login hand-off sent the token to any `returnTo` address (`uis/backoffice/app/login/page.tsx:46`, `register/page.tsx:67`) | A01 and A07 | Critical (likely, not tested in a browser) | Allow-list in `uis/backoffice/lib/returnTo.ts` | `infra/hardening/check_return_to.mjs` (11 of 11 checks pass), `returnto-before.txt`, `returnto-after.txt` (code lines) |
| 5 | `POST /knowledge/query` needed no login (`services/api/routes/knowledge.py:45`) | A01 and A04 | High | Login required | `knowledge-before.txt` (1 failed, 2 passed), `knowledge-after.txt` (3 passed) |
| 6 | Reporting routes, task status and the telemetry report needed no login | A01 | Medium | Login required | `reporting-before.txt` (5 failed, 2 passed), `reporting-after.txt` (7 passed) |
| 7 | Inventory product detail and order list needed no login (`services/api/routes/inventory.py:96`, `:201`) | A01 | Medium | Login required | `inventory-before.txt` (2 failed, 3 passed), `inventory-after.txt` (5 passed) |
| 8 | No limit on failed logins (`services/api/routes/auth.py:40-49`) | A07 | High | 5 failures per 15 minutes per email, then 429 | `login-before.txt` (2 failed, 2 passed), `login-after.txt` (4 passed) |
| 9 | CORS allowed any website (`services/api/main.py:76-81`) | A05 | Medium | Allow-list of known frontends and this Codespace | `cors-before.txt` (2 failed, 2 passed), `cors-after.txt` (4 passed) |
| 10 | `POST /telemetry/events` accepted any size (`services/api/routes/telemetry.py:92`) | A04 and A09 | Medium | 100 events and 256 KB per request, then 413 | `telemetry-limits-before.txt` (2 failed, 3 passed), `telemetry-limits-after.txt` (5 passed) |
| 11 | Redis, Qdrant and Flower published on all interfaces (`docker-compose.yml:48`, `:60`, `:102`) | A05 | High on a real server | Bound to `127.0.0.1` | `ports-before.txt`, `ports-after.txt`, `firewall-test.txt` |
| 12 | SSH root login on and other SSH rules unmet | A05 | Critical on a real server | Hardened config, shown in a container | `ssh-before.txt`, `ssh-after.txt` |
| 13 | Known vulnerabilities in `tornado` and `urllib3` (`services/api/uv.lock`) | A06 | Medium | Upgraded to `tornado` 6.5.10 and `urllib3` 2.8.0 | `dependency-audit.txt` (12 in 6 packages), `dependency-audit-after.txt` (6 in 4 packages) |

Part 1 (NIST) also fixed the model-call rate limit, hidden instructions in knowledge-base documents, and the RFP upload scan. See `docs/nist-security/nist-security-report.md`.

## 4. The 10 categories

### A01 Broken Access Control
| Lane | Applies? | What I found | Status |
| --- | --- | --- | --- |
| Backend | Yes | Several routes needed only a login or had no role check: users, suppliers, inventory, knowledge, reporting, tasks, telemetry report (fixes 1 to 3 and 5 to 7). | Fixed, except open items O1 to O3 and O13 |
| Frontend | Yes | The login hand-off could send the token to any address (fix 4). | Fixed, not tested in a browser |
| Agent | Yes | The agent's token is read-only by default (`services/api/agent/mcp_client.py:87`, and `MCP_SCOPES` is not set in `.env`). Each MCP tool checks its own scope (`mcps/incidents-inventory-tools/server.py:74`). The agent only calls `check_ticket_status` and `query_inventory` (`services/api/agent/nodes.py:150`, `:170`). Chat sessions belong to one user (`services/api/routes/chat_ws.py:91-96`). | Pass |

### A02 Cryptographic Failures
| Lane | Applies? | What I found | Status |
| --- | --- | --- | --- |
| Backend | Yes | Passwords use bcrypt, and login tokens last 30 minutes and use a fixed algorithm list (`services/api/security.py:29`, `:49`, `:65`). Reset tokens are stored as a SHA-256 hash (`:82-88`). The secret behind HS256 tokens is only as strong as the value in `.env`, and the code does not check its strength. I did not test HTTPS. | Partly checked |
| Frontend | Yes | Login tokens are kept in `localStorage` in all three login-using apps (`uis/backoffice/lib/auth.ts:10-18`, `uis/incidents/lib/auth.ts:13-21`, `uis/talent-pipeline-tracker/lib/auth.ts:13-21`). A script running on the page could read them. | Open, O5 |
| Agent | Yes | No keys in the code: a pattern scan matched 10 files and all were false positives (NIST report, section 5). The real `.env` files are git-ignored. The MCP client reads its secret from the environment and does not print it (`services/api/agent/mcp_client.py:70-92`). | Pass (none found, not proven none) |

### A03 Injection
| Lane | Applies? | What I found | Status |
| --- | --- | --- | --- |
| Backend | Yes | No SQL built with f-strings, and no `eval`, `exec`, `pickle.load` or `yaml.load` in `services`, `data`, `mcps` and `scripts` (Python files, tests excluded). Database calls use SQLModel `select(...)`. One `subprocess.run` in `scripts/nightly_export.py:134` runs our own pipeline, and I did not read its arguments. | Pass, one item not reviewed |
| Frontend | Yes | No `dangerouslySetInnerHTML`, `innerHTML` or `eval(` in the `.ts` and `.tsx` files under `uis`. | Pass |
| Agent | Yes | Prompt injection: jailbreak guard, cleaning of outside text, output guard (NIST report, section 5). Two gaps found and fixed in Part 1: instructions hidden in knowledge-base text, and the RFP upload scan. | Fixed |

### A04 Insecure Design
| Lane | Applies? | What I found | Status |
| --- | --- | --- | --- |
| Backend | Yes | Added limits: model calls (Part 1), failed logins (fix 8), telemetry size (fix 10). Still no rate limit on `services/api/routes/rfp.py:400` and `:430`, or on `POST /knowledge/query` (login only now). The telemetry report cache grows with every different date text (`services/api/routes/telemetry.py:66`). | Partly fixed, O7 and O10 |
| Frontend | Not separately assessed | No design review of the frontends beyond the items in this report. | Not checked |
| Agent | Yes | Of the irreversible actions in the CONTEXT file, mass campaigns, large supplier orders and Brasa Points changes are not built. Supplier status change exists as a backoffice route with no confirmation step (managers and admins only now). The agent has no path to it. | Pass for the agent |

### A05 Security Misconfiguration
| Lane | Applies? | What I found | Status |
| --- | --- | --- | --- |
| Backend | Yes | CORS allowed any site (fix 9). The API docs page is public because no `docs_url` is set (`services/api/main.py:64-69`). I found no `debug` setting. | Fixed, O11 open |
| Frontend | Not separately assessed | Only the CORS side was checked. | Not checked |
| Agent | Yes | The MCP server has token checking (`mcps/incidents-inventory-tools/server.py:219`) but listens on all interfaces (`:237`). Its port is not in `docker-compose.yml`. Server hardening is in section 2. | Partly fixed |

### A06 Vulnerable and Outdated Components
| Lane | Applies? | What I found | Status |
| --- | --- | --- | --- |
| Backend | Yes | `pip-audit` found 12 known vulnerabilities in 6 packages. I upgraded `tornado` and `urllib3` (6 left in 4 packages: `ecdsa`, `nltk`, `oauthlib`, `python-jose`). Only `python-jose` is a package we ask for directly (`services/api/pyproject.toml:10`). `oauthlib` needs a major upgrade (to 4.0.0), and the other three list no fix. I read only the start of each advisory. By their wording they likely do not apply to our use, but I did not verify that. | Partly fixed, O8 |
| Frontend | Yes | `npm audit` was not run. | Not checked, O9 |
| Agent | Yes | The agent libraries in `services/api` were part of the audit above. The MCP server runs in a separate environment (`fastmcp` is not installed in `services/api/.venv`) and was not audited. | Not checked, O9 |

### A07 Identification and Authentication Failures
| Lane | Applies? | What I found | Status |
| --- | --- | --- | --- |
| Backend | Yes | No limit on failed logins (fix 8). Login gives the same error for an unknown email and a wrong password (`services/api/routes/auth.py:42-46`). I did not measure the small speed difference that probably remains. Passwords need at least 8 characters (`services/api/user_models.py:34`). No multi-factor login. | Fixed (limit), O10 open |
| Frontend | Yes | Token hand-off through a URL fragment, and the address is wiped afterwards (`uis/incidents/components/RouteGuard.tsx:15-35`). The `returnTo` flaw is fixed (fix 4). | Fixed |
| Agent | Yes | The chat WebSocket takes the login token in the address (`?token=`, `services/api/routes/chat_ws.py:5-9`). Addresses can end up in server logs. The MCP client uses a client-credentials login with Logto. | Open, O4 |

### A08 Software and Data Integrity Failures
| Lane | Applies? | What I found | Status |
| --- | --- | --- | --- |
| Backend | Yes | The Docker build installs exactly what `services/api/uv.lock` says (`uv sync --frozen`, `services/Dockerfile:37`, `:47`). I updated that file for fix 13. Qdrant uses the `latest` tag (`docker-compose.yml:57`). | Partly fixed, O12 |
| Frontend | Yes | I did not review the frontend lock files. | Not checked |
| Agent | Yes | No unsafe loading found (see A03). Documents that could carry hidden instructions are checked before the model sees them (knowledge base and RFP upload, Part 1). | Pass |

### A09 Security Logging and Monitoring Failures
| Lane | Applies? | What I found | Status |
| --- | --- | --- | --- |
| Backend | Yes | Events are stored by `POST /telemetry/events`, which is open by design because login failures happen before a token exists (`services/api/routes/telemetry.py:5-9`). The sender's `userId` is not verified. My new login lockouts and rate-limit refusals are not logged. | Partly, O6 and O15 |
| Frontend | Yes | The frontend sends telemetry in batches of 20 (`uis/backoffice/lib/telemetry.ts:23`). | Pass |
| Agent | Yes | Guardrail events (`services/api/agent/guardrails/telemetry.py:46`), MCP tool calls (`@audited`), the memory audit log and agent traces all exist. The RFP upload scan result is on the ticket only (NIST report, gap G7). | Pass, one gap |

### A10 Server-Side Request Forgery
| Lane | Applies? | What I found | Status |
| --- | --- | --- | --- |
| Backend | Yes | There are only two outgoing web calls in the backend code I searched: `services/api/agent/mcp_client.py:79` and `mcps/incidents-inventory-tools/inventory_client.py:47`. Both addresses come from environment variables. No route takes a web address from a caller. | Pass |
| Frontend | No | The browser calls our own API only. | Not applicable |
| Agent | Partly | The MCP and token addresses are fixed by configuration. I did not check whether the PDF converter used for RFP uploads fetches addresses inside a document. | Not checked |

## 5. Open items (not fixed)

| # | Item | Risk | Proposed fix |
| --- | --- | --- | --- |
| O1 | `GET /inventory/products` needs no login, because the MCP server reads it without a token (`mcps/incidents-inventory-tools/inventory_client.py:48`) | Medium | Give the MCP server its own service token, then require a login |
| O2 | `POST /suppliers` (create) has no role check | Low to medium | Confirm how the backoffice uses it, then limit to managers and admins |
| O3 | `GET /rfp/events` has no role check, so any logged-in user sees every ticket event (`services/api/routes/rfp_events.py:99-114`) | Medium | Decide who should see them, then add a role check |
| O4 | The chat WebSocket token travels in the address | Medium | Use a short-lived one-time ticket |
| O5 | Login tokens in `localStorage` | Medium | Move to an httpOnly cookie |
| O6 | Telemetry `userId` is not verified, and the endpoint is open by design | Low to medium | Verify it when a token is present |
| O7 | The telemetry report cache has no size limit (now behind login) | Low | Cap the number of entries |
| O8 | 6 known vulnerabilities left in `ecdsa`, `nltk`, `oauthlib` and `python-jose` | Probably low, not verified | Re-check when fixed versions appear. Test the `oauthlib` 4.0.0 upgrade separately. |
| O9 | `npm audit` and the MCP server environment were not audited | Unknown | Run both |
| O10 | Rate-limit and login counts live in memory, and someone can lock out a known email by failing on purpose | Medium | Keep counts in Redis (`REDIS_URL` already exists) |
| O11 | The API docs page (`/docs`) is public | Low | Turn it off or protect it in production |
| O12 | `qdrant/qdrant:latest` is not pinned (`docker-compose.yml:57`) | Low | Pin a version |
| O13 | I could not see a password on Redis, Qdrant or Flower | Unknown | Check `.env` and set passwords |
| O14 | Routes in `routes/rfp.py`, `routes/rfp_approval.py` and `routes/incidents.py` were counted for login mentions, not read one by one | Unknown | Review each route |
| O15 | Lockouts and rate-limit refusals are not logged | Low | Log them as security events |
| O16 | Port 2000 in the Codespace is unidentified, and production HTTPS was not set up or tested | Unknown | Identify the port, set up HTTPS |

## 6. Test results

- API suite (`services/api/tests`): 83 passed. That is 40 existing tests plus 43 new: `test_access_control.py` (7), `test_supplier_access.py` (8), `test_cors.py` (4), `test_inventory_access.py` (5), `test_knowledge_access.py` (3), `test_reporting_access.py` (7), `test_telemetry_limits.py` (5), `test_login_limit.py` (4).
- `uis/backoffice/lib/returnTo.ts`: `node infra/hardening/check_return_to.mjs` passes 11 of 11 checks.
- Every new test file was run before its fix (failures shown) and after (all passing).
- The whole `tests/pipelines` suite (two files that need `matplotlib` excluded): 7 failed, 468 passed, 20 errors, the same counts as at the end of Part 1. The 7 failing tests (4 in `tests/pipelines/test_agent.py`, 3 in `tests/pipelines/test_agent_tools.py`) also fail on the code from before any of this work (7 failed, 2 passed in those two files). The 20 errors were also there before (an SQLite error on a `reporting.` table), and I did not fix them.

## 7. Limits of this audit

- This was a code and configuration review, not a penetration test. I did not run any frontend in a browser.
- I found things by searching for patterns. A search can miss things, and some outputs were capped.
- Ratings are my own judgement.
- Server hardening is shown in a container, not on a real server.
- I read only the first part of each dependency advisory.
