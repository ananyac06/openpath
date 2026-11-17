# OpenPath Product Specification
**Version 1.0 | India-first | Local-first | TUI-first**

---

## 1. Vision & Purpose

OpenPath is an **evidence-driven opportunity research engine** specifically engineered for students, freshers, and early-career technical candidates in India.

Traditional job search mechanisms fail students:
- Opportunities are fragmented across hundreds of company career sites, ATS platforms, GitHub discussions, and developer forums.
- Generic aggregators scrape listings without verification, publishing outdated, closed, duplicate, or fraudulent postings.
- Eligibility requirements are frequently miscommunicated or exaggerated (e.g., claiming "freshers welcome" when the post demands 3 years of experience, or assuming "remote" implies Indian applicants are legally eligible).

OpenPath solves this by functioning as an **investigative research instrument**, not a passive job board.

### Fundamental Principle
> **Search broadly. Investigate deeply. Verify independently. Publish conservatively.**

1. A company being genuine does not prove a particular job listing is genuine.
2. A genuine job listing does not prove it is currently accepting applications.
3. A valid opportunity does not automatically mean a particular candidate is eligible.
4. "Remote" does not automatically mean an Indian candidate is eligible.

---

## 2. Target Geography & Candidates

### Primary Geography
- **India**: All primary discovery, ATS scanning, corporate registry checks, and eligibility rules focus on candidates residing and authorized to work in India.
- **International & Remote**: Discovered only when Indian applicants are explicitly accepted or credible evidence establishes India-accessibility.

### Candidate Population
- First-year, second-year, third-year, and final-year undergraduate students.
- Recent graduates (0–2 years of formal professional experience).
- Skilled candidates without formal degrees or professional experience.
- Candidates from any university, college, or institute without artificial Tier-1 preferences. Institutional restrictions are recorded only when explicitly stated by the employer.

### Technical Disciplines & Extensible Taxonomy
- Computer Science & Information Technology
- Artificial Intelligence & Machine Learning
- Software Engineering (Backend, Frontend, Full-stack, Mobile)
- Data Science & Data Engineering
- Cloud Engineering, DevOps & Site Reliability Engineering (SRE)
- Cybersecurity & Systems Engineering
- Research Engineering & National Lab Fellowships

---

## 3. Opportunity Scope

OpenPath discovers and verifies:
1. **Paid internships**
2. **Unpaid internships** (transparently labelled; never silently suppressed or disguised)
3. **Full-time fresher positions** (0–2 years experience)
4. **Entry-level software engineering roles**
5. **Remote employment accepting Indian residents**
6. **International opportunities with explicit Indian eligibility**
7. **Research internships & assistantships**
8. **Apprenticeships & graduate trainee programs**
9. **Fellowship programs & developer grants**
10. **Open-source contribution programs & GSoC-affiliated opportunities**
11. **Technical hackathons and early-career development programs**

Compensation details are never fabricated; if not disclosed by the primary source, they are recorded as `"Not disclosed"`.

---

## 4. Strict Admission Gates & Classifications

Opportunities undergo independent verification stages and are classified into four strict categories:

1. **`VERIFIED`**:
   - Organization identity verified.
   - Source authority verified.
   - Listing existence confirmed.
   - Application destination confirmed to lead to an authorized, employer-controlled endpoint.
   - Currently active and accepting applications.
2. **`NEEDS_INVESTIGATION`**:
   - Potentially genuine, but at least one mandatory verification check is inconclusive or pending.
   - Never placed in the primary active feed until resolved.
3. **`COMMUNITY_LEAD`**:
   - Discovered via developer communities, Reddit, or social posts.
   - Serves as an investigation signal; cannot be promoted to `VERIFIED` without primary source confirmation.
4. **`REJECTED`**:
   - Proven fraudulent, expired, closed, inaccessible, or non-technical/out-of-scope.
   - Preserved in audit records; excluded from candidate feeds.

---

## 5. User Interface Hierarchy

1. **Primary Interface:** Textual Terminal User Interface (`openpath`). Rich keyboard-driven research console.
2. **Secondary Interface:** Command-Line Interface (`openpath <subcommand>`) via Typer for automated, scriptable, or pipeline runs.
3. **Tertiary / Optional Interface:** Local-only web viewer bound to `127.0.0.1` for inspecting research records in a browser. No external cloud dependencies or public web deployments.
