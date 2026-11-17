# Comparative Audit of Existing Open-Source Projects & ATS APIs
**Research Reference for OpenPath Development**

---

## 1. FreeHire (`strelov1/freehire`)
- **Architecture:** Go/Python hybrid pipeline crawling ATS endpoints (Greenhouse, Lever, Ashby, Workday, iCIMS).
- **Strengths:** 
  - Directly queries ATS endpoints instead of scraping Google/LinkedIn search results.
  - Basic deduplication across job boards.
  - MIT licensed, self-hostable.
- **Limitations & Differences from OpenPath:**
  - Lacks strict evidence traceability (claims are stored as raw text without granular evidence hashes or verification check logs).
  - Assumes any active listing is genuine without independent domain ownership or corporate registry verification.
  - Lacks India-specific candidate eligibility reasoning (degree, academic year, Tier-agnostic matching, India-accessibility validation).
  - No native terminal console (TUI).

---

## 2. Shelf (`ggambhirdev/shelf`)
- **Architecture:** Node/TypeScript aggregator focused on student internships and co-ops.
- **Strengths:**
  - Targets student internships specifically.
  - Generates concise markdown reports of new postings.
- **Limitations & Differences from OpenPath:**
  - Primarily targets US/Canada college timelines (Fall/Spring/Summer co-op terms).
  - Lacks persistent crawl frontier and database-backed audit log.
  - Does not evaluate Indian candidate eligibility or legal work authorization constraints.
  - Relies on static JSON files rather than an ACID-compliant local relational store with FTS.

---

## 3. Applicant Tracking System (ATS) Public APIs

### A. Greenhouse Job Board API
- **Base Endpoint:** `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`
- **Authentication:** Unauthenticated read access.
- **Structure:**
  - `jobs`: Array of job objects containing `id`, `title`, `updated_at`, `requisition_id`, `location.name`, `absolute_url`, `departments`, `offices`, and `content` (HTML).
  - `meta.total`: Total job count.
- **Single Job Detail:** `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{id}?questions=true`
- **Rate Limit Policy:** Standard HTTP 429 response on bursts; respects token-bucket rates of 2 requests/sec.

### B. Lever Postings API
- **Base Endpoint:** `https://api.lever.co/v0/postings/{company}?mode=json`
- **Authentication:** Unauthenticated read access.
- **Structure:**
  - Array of postings containing `id`, `text` (title), `hostedUrl`, `applyUrl`, `categories` (`commitment`, `department`, `location`, `team`), `descriptionPlain`, `descriptionHtml`, `lists` (responsibilities, requirements).
- **Rate Limit Policy:** 2 requests/sec.

### C. Ashby Job Board API
- **Base Endpoint:** `https://api.ashbyhq.com/posting-api/job-board/{board_name}?includeCompensation=true`
- **Authentication:** Unauthenticated read access.
- **Structure:**
  - `apiVersion`: String ("1").
  - `jobs`: Array of postings containing `title`, `location`, `secondaryLocations`, `department`, `team`, `isRemote`, `workplaceType`, `employmentType`, `publishedAt`, `jobUrl`, `applyUrl`, `descriptionHtml`, `descriptionPlain`, and `compensation` (salary ranges, currency, intervals).
- **Rate Limit Policy:** 2 requests/sec.
