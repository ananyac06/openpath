# AGENTS.md — Instructions for Autonomous & Assisting Engineers
**Project: OpenPath | Local-first, TUI-first, Evidence-driven Research Engine**

---

## 1. Prime Directive & Core Principles

OpenPath is a **research instrument**, not a superficial job aggregator or scraper.

Every engineer and agent working on this codebase must adhere to these non-negotiable rules:
1. **Never fabricate listings or data:** Production results must only contain genuine, verifiable data discovered from declared sources. Synthetic test records belong exclusively in `tests/fixtures/` and must be explicitly tagged as synthetic.
2. **Never infer missing eligibility:** If a job description does not mention an academic year, record `academic_year = UNKNOWN`. Never assume all years are eligible or that experience is not required.
3. **Never equate "remote" with "India eligible":** An international remote role requires explicit evidence that Indian residents are eligible to apply.
4. **Decouple verification from candidate eligibility:** An opportunity can be `VERIFIED` as genuine while a candidate's eligibility remains `UNCLEAR` or `INELIGIBLE`. Never reject a verified job simply because the candidate does not qualify.
5. **Traceability is mandatory:** Every factual assertion in an opportunity record must reference a valid `EvidenceRecord` with URL, timestamp, content hash, and excerpt.
6. **No bypass of access controls:** Respect `robots.txt`, HTTP 429/Retry-After, rate limits, and access policies. Never use proxy rotators, CAPTCHA bypasses, or credential stuffing.
7. **Zero mandatory cloud dependencies:** The system must run completely locally on Linux using SQLite (WAL mode). No cloud database or paid LLM API is required to launch or operate OpenPath.

---

## 2. Development & Tooling Commands

OpenPath uses modern Python tooling pinned via `uv`:

```bash
# Sync virtual environment & install dependencies
uv sync

# Run system diagnostics & database checks
uv run openpath doctor
uv run openpath database check

# Launch the primary Textual TUI research console
uv run openpath

# Run the test suite
uv run pytest

# Run fast linter & code formatting check
uv run ruff check .
uv run ruff format --check .

# Run static type checking
uv run pyright
```

---

## 3. Code Architecture & Conventions

- **Module Organization:**
  - `src/openpath/cli.py`: Typer CLI commands and entry points.
  - `src/openpath/config.py`: Local configuration (XDG standard dirs).
  - `src/openpath/db/`: SQLite connection manager, schema migrations, and repositories.
  - `src/openpath/models/`: Pydantic v2 domain schemas (Opportunity, Profile, Evidence, etc.).
  - `src/openpath/network/`: Asynchronous HTTPX client with SSRF protection, rate limiting, and backoff.
  - `src/openpath/connectors/`: Modular source connectors (Greenhouse, Lever, Ashby, Career Spider, GitHub, Reddit).
  - `src/openpath/extraction/`: lxml & Trafilatura text extraction, HTML cleaning, metadata parsing.
  - `src/openpath/verification/`: Independent verification gates (company identity, source authority, availability).
  - `src/openpath/eligibility/`: Candidate eligibility evaluation engine.
  - `src/openpath/dedup/`: Multi-signal deduplication and cluster manager.
  - `src/openpath/tui/`: Textual TUI screens and widgets.
- **Typing:** Strict typing throughout. All functions must have complete type signatures. Use Python 3.13+ typing features.
- **Error Handling:** Explicit exception classes derived from `OpenPathError`. No silent failures or bare `except:` blocks.
