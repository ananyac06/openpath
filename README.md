# OpenPath

Local-first, TUI-first, evidence-driven opportunity research for students, freshers
and early-career technical candidates in India.

OpenPath is not a job aggregator. It is a research instrument: it registers sources,
crawls them under explicit access rules, extracts structured opportunity facts,
independently verifies organisation identity and listing authenticity, evaluates
candidate eligibility, and keeps every claim traceable to evidence.

## Status

- **Phase 0 (Architecture & Audit):** Complete. See `docs/`.
- **Phase 1 (Local Foundation):** Complete. Typer CLI, Textual TUI with 14 screens/tabs, SQLite WAL + FTS5, schema migrations, system diagnostics (`openpath doctor`).
- **Phase 2 (End-to-End Vertical Slice):** Complete. Modular source registry, CrawlFrontier, Throttled `SafeHttpClient` with SSRF protection, live public ATS connectors (Greenhouse, Lever, Ashby), and verifiable evidence storage.
- **Phase 3 (Official Company Discovery):** Complete. Career page HTML spider, sitemap reader, ATS link auto-detection.
- **Phase 4 (Authenticity & Eligibility):** Complete. Non-speculative candidate eligibility matching, multi-signal deduplication and canonical tracking param stripper.
- **Phase 5 (Community & Technical Research):** Complete. GitHub open-source and Reddit connectors producing traceable `COMMUNITY LEAD` records.
- **Phase 6 (Document Research):** Complete. Sandboxed PDF extraction with byte caps and text stream parsing.
- **Phase 7 (Reference Benchmark):** Complete. Stratified 100-organisation benchmark (`data/benchmark_100_orgs.json`) with quantitative scorecard (`openpath report benchmark`).
- **Phase 8 (Secondary Web Inspector):** Complete. Local-only read-only HTTP viewer (`openpath serve` bound strictly to `127.0.0.1:8765`).
- **Phase 9 (Verified Directory & Scale):** Complete. 1,125+ authentic verified organizations across S&P 500 US leaders, BSE & NSE listed giants, tech unicorns, open-source foundations, and research institutes with dual-tab research viewer.

## Release Versions

- **v1.0.0 (`v1-opportunities` branch):** Grouped Opportunities View with 2,101 real job postings, company cards, sub-tables, and first-year student & zero-experience filter chips (`🎓 Internships`, `🌱 Zero-Exp`, `🚀 Student Combined`, `🌐 Remote`).
- **v1.1.0 (`main` branch):** Comprehensive Dual-View Console featuring both the 2,101 Live Roles and the 1,125+ Verified Organizations Directory with stock tickers, official careers links, interactive cross-linking, and category filtering.

No fabricated listings exist in the production database. Synthetic records are
confined to `tests/fixtures/` and are labelled as synthetic. Real listings in `openpath.db` are fetched and verified against live public sources.

## Quickstart

```bash
# Sync dependencies
uv sync

# Run health diagnostics
uv run openpath doctor

# Launch interactive Textual TUI (primary interface)
uv run openpath

# Run research on declared sources (e.g. Greenhouse or Lever)
uv run openpath research run --source ats.greenhouse.groww
uv run openpath research run --source ats.lever.meesho

# Explore discovered opportunities and evidence in CLI
uv run openpath results list
uv run openpath results inspect <opportunity-id>

# Run benchmark evaluation
uv run openpath report benchmark

# Launch local web inspector (optional secondary viewer)
uv run openpath serve --port 8765
```

## Quality Assurance

```bash
uv run pytest             # 31 passing unit and integration tests
uv run ruff check .       # Zero lint errors
uv run pyright            # Zero type errors, zero warnings
```

Python 3.13 is the minimum supported interpreter. Python 3.14 compatibility is
checked by the test suite before it is declared supported.

## Documentation

| Document | Purpose |
|---|---|
| `docs/PRODUCT_SPEC.md` | Product definition, scope, non-negotiables |
| `docs/ARCHITECTURE.md` | Stack decision record and component design |
| `docs/SOURCE_INVENTORY.md` | Source categories, access methods, status |
| `docs/VERIFICATION_POLICY.md` | Admission gates and evidence requirements |
| `docs/DATA_MODEL.md` | Entities, relationships, invariants |
| `docs/SECURITY_AND_ACCESS.md` | Local-first security and responsible access |
| `docs/BENCHMARK_PLAN.md` | Evaluation dataset and metrics |
| `docs/ROADMAP.md` | Phased implementation plan |
| `docs/research/` | Dated audits of external projects and APIs |

## Data locations

| Purpose | Default path |
|---|---|
| Config | `~/.config/openpath/config.toml` |
| Data (SQLite) | `~/.local/share/openpath/openpath.db` |
| State/logs | `~/.local/state/openpath/` |

Override with `OPENPATH_CONFIG_DIR`, `OPENPATH_DATA_DIR`, `OPENPATH_STATE_DIR`,
or `OPENPATH_DB_PATH`. No cloud account or API key is required to launch.
