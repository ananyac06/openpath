# OpenPath Source Inventory & Access Policy
**Version 1.0 | Source Registry & Connector Matrix**

---

## 1. Source Classification & Authority Tiers

Every source registered in OpenPath belongs to an explicit **Authority Tier**:

| Authority Tier | Description | Weight / Role in Verification |
|---|---|---|
| **`official`** | Company-owned domains, verified corporate sites, official press releases. | Highest authority for company identity and opportunity existence. |
| **`ats`** | Direct employer job boards on verified ATS infrastructure (Greenhouse, Lever, Ashby). | Primary authority for live application availability and destination checks. |
| **`registry`** | Official government corporate registries (MCA India, SEC EDGAR, Companies House). | Authoritative for company legal existence and registration status. |
| **`institutional`** | Government portals (AICTE, NCS), universities, national research labs (CSIR, IISc). | Authoritative for research internships, fellowships, and government apprenticeships. |
| **`community`** | Developer forums, Reddit, GitHub discussions, community job channels. | Investigative leads only (`COMMUNITY_LEAD`). Cannot independently verify an opportunity. |
| **`aggregator`** | Third-party job boards (LinkedIn, Indeed, Internshala, Wellfound). | Discovery leads. Opportunities must be resolved to direct employer application endpoints. |

---

## 2. Source Connectors Matrix

| Connector ID | Category | Provider / Platform | Access Method | Auth Required | Endpoints / Patterns | Policy & Rate Limits |
|---|---|---|---|---|---|---|
| `ats.greenhouse` | ATS | Greenhouse Job Board | Public REST API | None (Read-only) | `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true` | Max 2 req/s per board token. Respect `Retry-After`. |
| `ats.lever` | ATS | Lever Postings | Public REST API | None (Read-only) | `https://api.lever.co/v0/postings/{company}?mode=json` | Max 2 req/s per company slug. Respect `Retry-After`. |
| `ats.ashby` | ATS | Ashby Job Board | Public REST API | None (Read-only) | `https://api.ashbyhq.com/posting-api/job-board/{board_name}?includeCompensation=true` | Max 2 req/s per board slug. Respect `Retry-After`. |
| `web.career_spider` | Official | Company Career Pages | HTTPX HTML + Trafilatura | None | Company career URLs, `sitemap.xml`, `/careers`, `/jobs` | Robots.txt respected. Per-domain budget: 1 req/s. Max crawl depth: 2. |
| `vcs.github` | Open Source | GitHub API | Official REST API | Optional (Bearer token increases rate limit) | `https://api.github.com/orgs/{org}/repos`, Issue Search API | 60 req/hr unauthenticated; 5,000 req/hr with personal token. |
| `social.reddit` | Community | Reddit API | Official OAuth / API | Client ID + Secret (free tier) | `https://oauth.reddit.com/r/{subreddit}/hot` | Max 60 req/min. Post deletion and retention policies strictly enforced. |
| `gov.aicte` | Institutional | AICTE Internship Portal | Public Web Catalog | None | `https://internship.aicte-india.org` | Periodic batch check; strictly respectful request intervals. |

---

## 3. Initial Source Inventory (Seed Connectors & Boards)

### A. Greenhouse Boards (Sample India & Global Seed)
1. **Groww** (`groww`): Top Indian fintech. `https://boards-api.greenhouse.io/v1/boards/groww/jobs?content=true`
2. **Slice** (`slice`): Indian consumer tech & payments. `https://boards-api.greenhouse.io/v1/boards/slice/jobs?content=true`
3. **GitLab** (`gitlab`): Global all-remote developer platform hiring in India. `https://boards-api.greenhouse.io/v1/boards/gitlab/jobs?content=true`

### B. Lever Boards (Sample India Seed)
1. **Meesho** (`meesho`): Indian e-commerce unicorn. `https://api.lever.co/v0/postings/meesho?mode=json`
2. **CRED** (`cred`): Indian premium fintech. `https://api.lever.co/v0/postings/cred?mode=json`

### C. Ashby Boards (Sample India & Global Seed)
1. **Atlan** (`atlan`): Global active metadata platform with major engineering hub in India. `https://api.ashbyhq.com/posting-api/job-board/atlan`
2. **PostHog** (`posthog`): Open-source product engineering platform with remote hiring. `https://api.ashbyhq.com/posting-api/job-board/posthog`

---

## 4. Policy Compliance & Responsible Access Rules

1. **No Circumvention:** Never use rotating proxy services to evade rate limits, never bypass CAPTCHAs, and never spoof user identities.
2. **Robots.txt Adherence:** Automatically check and honor `robots.txt` directives for custom web crawling.
3. **Conditional Requests:** Send `If-None-Match` (ETag) and `If-Modified-Since` headers to avoid downloading unchanged listings.
4. **Circuit Breakers:** If a source encounters consecutive 4xx/5xx errors (threshold: 3 consecutive errors or HTTP 429), pause the source for exponential backoff intervals (starting at 60s up to 1 hour).
5. **Ledger Recording:** Every access attempt, success, rate limit encounter, and failure is recorded in `source_access_ledger` for user transparency.
