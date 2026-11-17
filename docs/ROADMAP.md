# OpenPath Phased Implementation Roadmap
**Version 1.0 | Milestone Definitions & Acceptance Criteria**

---

## Roadmap Overview

```
Phase 0: Technical Audit & Specifications (Done)
   ↓
Phase 1: Local Foundation (CLI, TUI, SQLite, Doctor, Diagnostics)
   ↓
Phase 2: First End-to-End Pipeline (Frontier, HTTPX, Greenhouse, Lever, Ashby, Evidence Store)
   ↓
Phase 3: Official Company Discovery (Career Spiders, Sitemaps, ATS Link Detection)
   ↓
Phase 4: Authenticity & Eligibility Engines (Verification Gates, Match Evaluator, Deduplication)
   ↓
Phase 5: Community & Institutional Leads (GitHub, Reddit, AICTE, Leads Admission)
   ↓
Phase 6: Document Research & Advanced Crawling (PDF Extractor, Playwright Fallback, Resumable Scans)
   ↓
Phase 7: Evaluation & Benchmark Suite (Reference Dataset, Precision/Recall Scorecard)
   ↓
Phase 8: Local Read-Only Results Viewer (127.0.0.1 Web Server)
```

---

## Detailed Milestone Definitions

### Phase 0: Repository & Technical Audit (Current)
- Complete technical audit of existing Linux environment, python dependencies, and existing projects (FreeHire, Shelf, ATS APIs).
- Deliverables: `docs/PRODUCT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/SOURCE_INVENTORY.md`, `docs/VERIFICATION_POLICY.md`, `docs/DATA_MODEL.md`, `docs/SECURITY_AND_ACCESS.md`, `docs/BENCHMARK_PLAN.md`, `docs/ROADMAP.md`, `AGENTS.md`.

### Phase 1: Local Application Foundation
- Set up modular package structure under `src/openpath/` and `tests/`.
- Local configuration (`config.py`) respecting XDG standard paths.
- Local SQLite database manager (`db/`) with WAL mode, foreign keys, busy timeout, and schema migrations.
- System diagnostics command (`openpath doctor` and `openpath database check`).
- Working Typer CLI (`cli.py`).
- Working Textual TUI (`tui/`) with keyboard navigation and 14 primary screens.
- Acceptance: `openpath doctor` and `openpath` run cleanly without external dependencies. Unit tests pass with `uv run pytest`.

### Phase 2: First End-to-End Research Pipeline
- Source Registry (`sources/`) with authority tiers and rate-limiting budgets.
- Persistent crawl frontier (`crawler/frontier.py`) tracking tasks and states.
- HTTPX networking layer (`network/`) with adaptive throttling, exponential backoff, retry-after, and SSRF prevention.
- ATS Connectors (`connectors/`) for Greenhouse, Lever, and Ashby using verified public APIs.
- Extraction & normalisation (`extraction/`) with lxml and Trafilatura.
- Evidence store (`evidence/`) linking claims to verified excerpts and content hashes.
- Acceptance: Real public ATS board queried, real job extracted, stored with evidence, and inspectable in CLI and TUI.

### Phase 3: Official Company Discovery
- Career page spider, sitemap index traversal, and link graph extraction.
- Automatic ATS board identification (discovering Greenhouse/Lever/Ashby links from company websites).
- Search provider abstraction interface.
- Acceptance: System discovers and registers ATS board endpoints directly from official company domains.

### Phase 4: Authenticity & Candidate Eligibility Engines
- Independent verification gates (`verification/`): company identity, source authority, listing existence, application destination, availability.
- Candidate eligibility engine (`eligibility/`): evaluating academic year, degree, experience, skills, and India authorization without speculative inference.
- Multi-signal deduplicator (`dedup/`): grouping duplicate postings while preserving provenance.
- Acceptance: Verified feed contains only opportunities passing all 5 core gates. Eligibility reports what is confirmed vs unknown.

### Phase 5: Community & Institutional Leads
- Official GitHub API connector (org repos, issues, announcements).
- Reddit API connector for technical Indian subreddits (`r/developersIndia`, `r/cscareerquestions`) with strict retention/deletion compliance.
- Institutional connectors (AICTE internship portal, national research labs).
- Admission gate: Community items admitted strictly as `COMMUNITY_LEAD` until officially verified.

### Phase 6: Document Research & Advanced Crawling
- Safe PDF extraction for recruitment notifications and fellowship prospectuses.
- Optional Playwright headless browser fallback for JavaScript-rendered career portals.
- Resumable crawls and incremental refresh mode.

### Phase 7: Benchmark Evaluation & Acceptance
- Benchmark run against the 100-company reference dataset.
- Quantitative report: verified precision, recall, eligibility precision, duplicate survival rate.

### Phase 8: Local Read-Only Results Viewer
- Optional local web viewer bound strictly to `127.0.0.1` reading directly from `openpath.db`.
