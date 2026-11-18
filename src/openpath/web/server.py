"""Local-only read-only web server for inspecting research results and evidence in a browser."""

from __future__ import annotations

import html
import logging
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from openpath.config import Config
from openpath.db.connection import DatabaseManager
from openpath.db.repository import Repository
from openpath.models.entities import Opportunity

logger = logging.getLogger(__name__)

INTERN_REGEX = re.compile(r"\b(intern|internship|summer|winter|trainee|apprentice|co-op)\b", re.IGNORECASE)
ENTRY_REGEX = re.compile(
    r"\b(junior|entry|associate|graduate|fresher|l1|level 1|beginner|early career)\b",
    re.IGNORECASE,
)

COMPANY_METADATA: dict[str, dict[str, str]] = {
    "Cloudflare": {
        "ticker": "NYSE: NET • S&P 500 Leader",
        "category": "us_sp500",
        "avatar": "CF",
        "color": "#f38020",
    },
    "MongoDB": {
        "ticker": "NASDAQ: MDB • Global Cloud Database Leader",
        "category": "us_sp500",
        "avatar": "MD",
        "color": "#00ed64",
    },
    "Elastic": {
        "ticker": "NYSE: ESTC • Search & AI Observability Leader",
        "category": "us_sp500",
        "avatar": "EL",
        "color": "#005571",
    },
    "Canonical": {
        "ticker": "Ubuntu Linux & Open Source Enterprise",
        "category": "open_source",
        "avatar": "CA",
        "color": "#e95420",
    },
    "GitLab": {
        "ticker": "NASDAQ: GTLB • The DevSecOps Platform",
        "category": "us_sp500",
        "avatar": "GL",
        "color": "#fc6d26",
    },
    "Mozilla": {
        "ticker": "Firefox, Rust & Open Web Foundation",
        "category": "open_source",
        "avatar": "MZ",
        "color": "#ff7139",
    },
    "Supabase": {
        "ticker": "Y-Combinator Open Source Cloud Unicorn",
        "category": "developer_platforms",
        "avatar": "SB",
        "color": "#3ecf8e",
    },
    "Meesho": {
        "ticker": "Top Indian E-Commerce Unicorn (Bengaluru)",
        "category": "indian_tech",
        "avatar": "ME",
        "color": "#f43397",
    },
    "CRED": {
        "ticker": "Top Indian Fintech Unicorn (Bengaluru)",
        "category": "indian_tech",
        "avatar": "CR",
        "color": "#212529",
    },
    "Groww": {
        "ticker": "BSE/NSE Registered Indian Wealthtech Leader",
        "category": "indian_tech",
        "avatar": "GW",
        "color": "#00d09c",
    },
    "PostHog": {
        "ticker": "Open Source Product Analytics Platform",
        "category": "developer_platforms",
        "avatar": "PH",
        "color": "#ffd000",
    },
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenPath Local Research Viewer</title>
    <style>
        :root {
            --bg: #0d1117;
            --card-bg: #161b22;
            --border: #30363d;
            --border-muted: #21262d;
            --text-main: #c9d1d9;
            --text-muted: #8b949e;
            --accent: #58a6ff;
            --green: #238636;
            --green-text: #3fb950;
            --green-border: rgba(63, 185, 80, 0.3);
            --green-bg: rgba(63, 185, 80, 0.1);
            --amber-text: #d29922;
            --amber-bg: rgba(210, 153, 34, 0.1);
            --purple-text: #bc8cff;
            --purple-bg: rgba(188, 140, 255, 0.1);
            --orange-text: #f0883e;
            --orange-bg: rgba(240, 136, 62, 0.1);
        }
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text-main);
            margin: 0;
            padding: 24px;
            line-height: 1.5;
        }
        .container { max-width: 1280px; margin: 0 auto; }
        header {
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }
        h1 { color: var(--accent); margin: 0; font-size: 24px; display: flex; align-items: center; gap: 8px; }
        .tag-pill {
            background: var(--green);
            color: white;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.5px;
        }

        /* Student Guide Banner */
        .student-guide-banner {
            background: linear-gradient(135deg, rgba(35, 134, 54, 0.15), rgba(88, 166, 255, 0.15));
            border: 1px solid rgba(88, 166, 255, 0.3);
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 20px;
            display: flex;
            gap: 16px;
            align-items: flex-start;
        }
        .student-guide-icon { font-size: 28px; line-height: 1; }
        .student-guide-content h3 { margin: 0 0 6px; font-size: 16px; color: #58a6ff; font-weight: 700; }
        .student-guide-content p { margin: 0; font-size: 13px; color: #c9d1d9; line-height: 1.4; }

        /* Stats Bar */
        .stats-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 14px;
            display: flex;
            flex-direction: column;
        }
        .stat-value { font-size: 22px; font-weight: bold; color: #f0f6fc; }
        .stat-label { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

        /* Category Filter Tabs */
        .filter-tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
            flex-wrap: wrap;
        }
        .tab-btn {
            background: var(--card-bg);
            color: var(--text-muted);
            border: 1px solid var(--border);
            padding: 7px 14px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.15s ease;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .tab-btn:hover { background: #21262d; color: #f0f6fc; border-color: #484f58; }
        .tab-btn.active {
            background: var(--accent);
            color: #0d1117;
            border-color: var(--accent);
            font-weight: 700;
        }
        .tab-count {
            background: rgba(255, 255, 255, 0.15);
            padding: 1px 7px;
            border-radius: 10px;
            font-size: 11px;
        }
        .tab-btn.active .tab-count {
            background: rgba(0, 0, 0, 0.25);
            color: #0d1117;
        }

        /* Toolbar */
        .toolbar {
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
            align-items: center;
            flex-wrap: wrap;
        }
        .search-box {
            display: flex;
            gap: 8px;
            flex-grow: 1;
        }
        input[type="text"] {
            background: var(--card-bg);
            border: 1px solid var(--border);
            color: var(--text-main);
            padding: 9px 14px;
            border-radius: 6px;
            flex-grow: 1;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }
        input[type="text"]:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.2);
        }
        .btn {
            background: #21262d;
            color: #c9d1d9;
            border: 1px solid var(--border);
            padding: 9px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            white-space: nowrap;
        }
        .btn:hover { background: #30363d; color: #fff; }
        .btn-primary { background: var(--green); border-color: rgba(240, 246, 252, 0.1); color: #fff; }
        .btn-primary:hover { background: #2ea043; }

        /* Grouped Company Cards */
        .company-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            margin-bottom: 14px;
            overflow: hidden;
            transition: border-color 0.2s;
        }
        .company-card:hover { border-color: #484f58; }
        .company-summary {
            padding: 12px 18px;
            cursor: pointer;
            list-style: none;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #1c2128;
            border-bottom: 1px solid transparent;
            user-select: none;
        }
        .company-summary::-webkit-details-marker { display: none; }
        details[open] > .company-summary {
            border-bottom-color: var(--border-muted);
        }
        .company-header-left {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        .company-avatar {
            width: 34px;
            height: 34px;
            border-radius: 6px;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 14px;
        }
        .company-title-block {
            display: flex;
            flex-direction: column;
        }
        .company-title {
            font-size: 16px;
            font-weight: 700;
            color: #f0f6fc;
            margin: 0;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .company-ticker {
            font-size: 11px;
            color: var(--text-muted);
            font-weight: 500;
        }
        .company-badges {
            display: flex;
            gap: 8px;
            align-items: center;
        }
        .chevron {
            transition: transform 0.2s ease;
            color: var(--text-muted);
            font-size: 12px;
        }
        details[open] .chevron {
            transform: rotate(180deg);
        }

        /* Subtable of Opportunities */
        .opportunities-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        .opportunities-table th {
            text-align: left;
            padding: 9px 18px;
            background: #161b22;
            color: var(--text-muted);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--border-muted);
        }
        .opportunities-table td {
            padding: 9px 18px;
            border-bottom: 1px solid var(--border-muted);
            vertical-align: middle;
        }
        .opportunities-table tr:last-child td { border-bottom: none; }
        .opportunities-table tr:hover td { background: #1f242c; }

        .role-title {
            color: #f0f6fc;
            font-weight: 600;
            text-decoration: none;
            display: inline-block;
        }
        .role-title:hover { color: var(--accent); text-decoration: underline; }

        /* Badges */
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            white-space: nowrap;
        }
        .badge-verified {
            background: var(--green-bg);
            color: var(--green-text);
            border: 1px solid var(--green-border);
        }
        .badge-lead {
            background: var(--amber-bg);
            color: var(--amber-text);
            border: 1px solid rgba(210, 153, 34, 0.3);
        }
        .badge-internship {
            background: rgba(245, 158, 11, 0.15);
            color: #f59e0b;
            border: 1px solid rgba(245, 158, 11, 0.4);
            font-weight: 700;
        }
        .badge-entry {
            background: rgba(16, 185, 129, 0.15);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.4);
            font-weight: 700;
        }
        .badge-fellowship {
            background: var(--purple-bg);
            color: var(--purple-text);
            border: 1px solid rgba(188, 140, 255, 0.3);
        }
        .badge-onsite {
            background: #21262d;
            color: #8b949e;
            border: 1px solid #30363d;
        }
        .badge-remote {
            background: rgba(56, 139, 253, 0.12);
            color: #58a6ff;
            border: 1px solid rgba(56, 139, 253, 0.3);
        }
        .badge-hybrid {
            background: var(--purple-bg);
            color: var(--purple-text);
            border: 1px solid rgba(188, 140, 255, 0.3);
        }
        .badge-count {
            background: #30363d;
            color: #f0f6fc;
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 12px;
            font-weight: 600;
        }
        .btn-apply {
            background: rgba(56, 139, 253, 0.1);
            color: #58a6ff;
            border: 1px solid rgba(56, 139, 253, 0.3);
            padding: 4px 10px;
            border-radius: 5px;
            font-size: 12px;
            text-decoration: none;
            font-weight: 600;
            transition: all 0.15s;
            white-space: nowrap;
        }
        .btn-apply:hover {
            background: #1f6feb;
            color: #fff;
            border-color: #1f6feb;
        }
        .empty-state {
            text-align: center;
            padding: 48px;
            color: var(--text-muted);
            background: var(--card-bg);
            border: 1px dashed var(--border);
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>OpenPath Research Console</h1>
                <p style="margin: 4px 0 0; color: #8b949e; font-size: 13px;">Local-first • India-first • Evidence-driven Opportunity Research</p>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                <span class="tag-pill">127.0.0.1 Local Only</span>
            </div>
        </header>

        <!-- Student Guidance Banner -->
        <div class="student-guide-banner">
            <div class="student-guide-icon">🌱</div>
            <div class="student-guide-content">
                <h3>First-Year Student & Zero-Experience Opportunity Hub</h3>
                <p>
                    Looking for your first tech internship, project apprenticeship, or beginner learning role?
                    Click <strong>🎓 Internships & Trainees</strong> or <strong>🌱 Zero-Exp & Entry-Level</strong> below to instantly filter for Software Engineering Internships (Summer/Winter), graduate trainee positions, and associate roles across S&P 500 tech leaders, open-source giants, and top product companies!
                </p>
            </div>
        </div>

        <!-- Stats Overview -->
        <div class="stats-bar">
            <div class="stat-card">
                <span class="stat-value">{total_companies}</span>
                <span class="stat-label">Verified Organizations</span>
            </div>
            <div class="stat-card">
                <span class="stat-value">{total_opportunities}</span>
                <span class="stat-label">Total Opportunities Ingested</span>
            </div>
            <div class="stat-card">
                <span class="stat-value" style="color: #f59e0b;">{internship_count}</span>
                <span class="stat-label">Internships & Apprenticeships</span>
            </div>
            <div class="stat-card">
                <span class="stat-value" style="color: #10b981;">{entry_count}</span>
                <span class="stat-label">Zero-Exp & Entry-Level Roles</span>
            </div>
            <div class="stat-card">
                <span class="stat-value" style="color: #58a6ff;">{remote_count}</span>
                <span class="stat-label">Remote & Hybrid Positions</span>
            </div>
        </div>

        <!-- Filter Chips / Tabs -->
        <div class="filter-tabs">
            <button type="button" class="tab-btn active" onclick="setCategoryFilter('all', this)">
                🌟 All Opportunities <span class="tab-count">{total_opportunities}</span>
            </button>
            <button type="button" class="tab-btn" onclick="setCategoryFilter('internship', this)">
                🎓 Internships & Trainees <span class="tab-count">{internship_count}</span>
            </button>
            <button type="button" class="tab-btn" onclick="setCategoryFilter('entry_level', this)">
                🌱 Zero-Exp & Entry-Level <span class="tab-count">{entry_count}</span>
            </button>
            <button type="button" class="tab-btn" onclick="setCategoryFilter('student_friendly', this)">
                🚀 Student & 0-Exp Combined <span class="tab-count">{student_friendly_count}</span>
            </button>
            <button type="button" class="tab-btn" onclick="setCategoryFilter('remote', this)">
                🌐 Remote & Hybrid <span class="tab-count">{remote_count}</span>
            </button>
            <button type="button" class="tab-btn" onclick="setCategoryFilter('us_sp500', this)">
                🏢 S&P 500 / US Listed <span class="tab-count">{sp500_count}</span>
            </button>
            <button type="button" class="tab-btn" onclick="setCategoryFilter('indian_tech', this)">
                🇮🇳 Indian Tech & Unicorns <span class="tab-count">{indian_tech_count}</span>
            </button>
        </div>

        <!-- Controls Toolbar -->
        <div class="toolbar">
            <form method="GET" class="search-box">
                <input type="text" id="searchInput" name="q" value="{query}" placeholder="Search opportunities by title, company, skills, or location...">
                <button type="submit" class="btn btn-primary">Search</button>
                {clear_btn}
            </form>
            <button type="button" class="btn" onclick="toggleAllCards()">Toggle All</button>
        </div>

        <!-- Company Cards List -->
        <div id="companyList">
            {cards}
        </div>
    </div>

    <script>
        let currentCategory = 'all';

        function setCategoryFilter(cat, btn) {
            currentCategory = cat;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');
            applyFilters();
        }

        function toggleAllCards() {
            const cards = document.querySelectorAll('details.company-card');
            if (!cards.length) return;
            const anyOpen = Array.from(cards).some(c => c.open);
            cards.forEach(c => c.open = !anyOpen);
        }

        function applyFilters() {
            const searchVal = document.getElementById('searchInput').value.toLowerCase().trim();
            const cards = document.querySelectorAll('.company-card');

            cards.forEach(card => {
                const companyName = (card.getAttribute('data-company') || '').toLowerCase();
                const companyCat = card.getAttribute('data-category') || '';
                const rows = card.querySelectorAll('.opp-row');
                let visibleRowsCount = 0;

                rows.forEach(row => {
                    const rowRoleType = row.getAttribute('data-role-type') || '';
                    const rowWorkMode = (row.getAttribute('data-work-mode') || '').toLowerCase();
                    const text = row.innerText.toLowerCase();

                    const matchesText = !searchVal || text.includes(searchVal) || companyName.includes(searchVal);

                    let matchesCategory = false;
                    if (currentCategory === 'all') {
                        matchesCategory = true;
                    } else if (currentCategory === 'internship') {
                        matchesCategory = (rowRoleType === 'internship');
                    } else if (currentCategory === 'entry_level') {
                        matchesCategory = (rowRoleType === 'entry_level');
                    } else if (currentCategory === 'student_friendly') {
                        matchesCategory = (rowRoleType === 'internship' || rowRoleType === 'entry_level' || rowRoleType === 'fellowship');
                    } else if (currentCategory === 'remote') {
                        matchesCategory = (rowWorkMode === 'remote' || rowWorkMode === 'hybrid');
                    } else if (currentCategory === 'us_sp500') {
                        matchesCategory = (companyCat === 'us_sp500');
                    } else if (currentCategory === 'indian_tech') {
                        matchesCategory = (companyCat === 'indian_tech');
                    }

                    if (matchesText && matchesCategory) {
                        row.style.display = '';
                        visibleRowsCount++;
                    } else {
                        row.style.display = 'none';
                    }
                });

                if (visibleRowsCount > 0) {
                    card.style.display = '';
                    if (currentCategory !== 'all' || searchVal) {
                        card.open = true;
                    }
                } else {
                    card.style.display = 'none';
                }

                const countBadge = card.querySelector('.company-visible-count');
                if (countBadge) {
                    countBadge.innerText = `${visibleRowsCount} matching`;
                }
            });
        }

        // Fast Client-Side Real-Time Filter
        const input = document.getElementById('searchInput');
        input.addEventListener('input', applyFilters);
    </script>
</body>
</html>
"""


def classify_opportunity(o: Opportunity) -> tuple[str, str, str]:
    """Classify an opportunity into (role_type_slug, badge_text, badge_class)."""
    title = (o.title or "").strip()
    ltitle = title.lower()

    if INTERN_REGEX.search(ltitle):
        return ("internship", "🎓 Internship", "badge-internship")
    elif ENTRY_REGEX.search(ltitle):
        return ("entry_level", "🌱 Entry-Level / 0-Exp", "badge-entry")
    elif "fellow" in ltitle:
        return ("fellowship", "💡 Fellowship", "badge-fellowship")
    else:
        return ("professional", "💼 Full-Time", "badge-onsite")


class LocalViewerHandler(BaseHTTPRequestHandler):
    config: Config
    repo: Repository

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        search_query = params.get("q", [None])[0]

        opps = self.repo.list_opportunities(search_query=search_query, limit=10000)

        # Group opportunities by company_name
        grouped: dict[str, list[Opportunity]] = {}
        for o in opps:
            grouped.setdefault(o.company_name, []).append(o)

        cards_html: list[str] = []
        verified_count = sum(1 for o in opps if o.admission_class == "VERIFIED")
        internship_count = 0
        entry_count = 0
        student_friendly_count = 0
        remote_count = 0
        sp500_count = 0
        indian_tech_count = 0

        for company_name, company_opps in sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True):
            meta = COMPANY_METADATA.get(company_name, {})
            ticker = meta.get("ticker", "Authoritative Declared Source")
            category = meta.get("category", "general")
            initial = meta.get("avatar") or (company_name[:2].upper() if company_name else "OP")
            avatar_color = meta.get("color") or "#238636"
            total_jobs = len(company_opps)

            onsite_cnt = sum(1 for o in company_opps if o.work_mode.value == "onsite")
            remote_cnt = sum(1 for o in company_opps if o.work_mode.value == "remote")
            hybrid_cnt = sum(1 for o in company_opps if o.work_mode.value == "hybrid")

            company_intern_cnt = 0
            company_entry_cnt = 0

            rows_html: list[str] = []
            for o in company_opps:
                role_type, role_badge_text, role_badge_class = classify_opportunity(o)

                if role_type == "internship":
                    internship_count += 1
                    company_intern_cnt += 1
                    student_friendly_count += 1
                elif role_type == "entry_level":
                    entry_count += 1
                    company_entry_cnt += 1
                    student_friendly_count += 1
                elif role_type == "fellowship":
                    student_friendly_count += 1

                if o.work_mode.value in ("remote", "hybrid"):
                    remote_count += 1

                if category == "us_sp500":
                    sp500_count += 1
                elif category == "indian_tech":
                    indian_tech_count += 1

                badge_cls = "badge-verified" if o.admission_class == "VERIFIED" else "badge-lead"
                mode_cls = (
                    f"badge-{o.work_mode.value}"
                    if o.work_mode.value in ("remote", "hybrid", "onsite")
                    else "badge-onsite"
                )

                rows_html.append(
                    f"<tr class='opp-row' data-role-type='{role_type}' data-work-mode='{o.work_mode.value}'>"
                    f"<td><a class='role-title' href='{html.escape(o.application_url)}' target='_blank' rel='noopener noreferrer'>{html.escape(o.title)}</a></td>"
                    f"<td><span class='badge {role_badge_class}'>{html.escape(role_badge_text)}</span></td>"
                    f"<td>{html.escape(o.location_raw or 'Not disclosed')}</td>"
                    f"<td><span class='badge {mode_cls}'>{html.escape(o.work_mode.value)}</span></td>"
                    f"<td><span class='badge {badge_cls}'>{html.escape(o.admission_class)}</span></td>"
                    f"<td style='text-align:right;'><a class='btn-apply' href='{html.escape(o.application_url)}' target='_blank' rel='noopener noreferrer'>Apply ↗</a></td>"
                    f"</tr>"
                )

            mode_badges = []
            if company_intern_cnt:
                mode_badges.append(
                    f"<span class='badge badge-internship'>{company_intern_cnt} Internships</span>"
                )
            if company_entry_cnt:
                mode_badges.append(
                    f"<span class='badge badge-entry'>{company_entry_cnt} Entry-Level</span>"
                )
            if remote_cnt:
                mode_badges.append(f"<span class='badge badge-remote'>{remote_cnt} Remote</span>")
            if hybrid_cnt:
                mode_badges.append(f"<span class='badge badge-hybrid'>{hybrid_cnt} Hybrid</span>")
            if onsite_cnt:
                mode_badges.append(f"<span class='badge badge-onsite'>{onsite_cnt} Onsite</span>")

            cards_html.append(
                f"<details open class='company-card' data-company='{html.escape(company_name)}' data-category='{html.escape(category)}'>\n"
                f"  <summary class='company-summary'>\n"
                f"    <div class='company-header-left'>\n"
                f"      <div class='company-avatar' style='background: {avatar_color};'>{initial}</div>\n"
                f"      <div class='company-title-block'>\n"
                f"        <h2 class='company-title'>{html.escape(company_name)} <span class='company-ticker'>({html.escape(ticker)})</span></h2>\n"
                f"      </div>\n"
                f"      <span class='badge-count'>{total_jobs} positions</span>\n"
                f"    </div>\n"
                f"    <div class='company-badges'>\n"
                f"      {' '.join(mode_badges)}\n"
                f"      <span class='chevron'>▼</span>\n"
                f"    </div>\n"
                f"  </summary>\n"
                f"  <div class='company-body'>\n"
                f"    <table class='opportunities-table'>\n"
                f"      <thead>\n"
                f"        <tr>\n"
                f"          <th>Opportunity Role / Title</th>\n"
                f"          <th style='width: 140px;'>Role Type</th>\n"
                f"          <th>Location</th>\n"
                f"          <th style='width: 90px;'>Work Mode</th>\n"
                f"          <th style='width: 100px;'>Admission</th>\n"
                f"          <th style='width: 90px; text-align:right;'>Action</th>\n"
                f"        </tr>\n"
                f"      </thead>\n"
                f"      <tbody>\n"
                f"        {''.join(rows_html)}\n"
                f"      </tbody>\n"
                f"    </table>\n"
                f"  </div>\n"
                f"</details>"
            )

        if not cards_html:
            cards_output = "<div class='empty-state'><h3>No opportunities found</h3><p>Try refining your search keyword or run new source discovery.</p></div>"
        else:
            cards_output = "\n".join(cards_html)

        clear_btn = (
            "<a href='/' class='btn' style='margin-left: 4px;'>Clear</a>" if search_query else ""
        )

        body = (
            HTML_TEMPLATE.replace("{total_companies}", str(len(grouped)))
            .replace("{total_opportunities}", f"{len(opps):,}")
            .replace("{verified_count}", f"{verified_count:,}")
            .replace("{internship_count}", str(internship_count))
            .replace("{entry_count}", str(entry_count))
            .replace("{student_friendly_count}", str(student_friendly_count))
            .replace("{remote_count}", str(remote_count))
            .replace("{sp500_count}", str(sp500_count))
            .replace("{indian_tech_count}", str(indian_tech_count))
            .replace("{query}", html.escape(search_query or ""))
            .replace("{clear_btn}", clear_btn)
            .replace("{cards}", cards_output)
            .encode("utf-8")
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s - - [%s] %s\n", self.address_string(), self.log_date_time_string(), format % args)


def run_server(config: Config, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Launch the local read-only web inspector."""
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError(
            f"Security violation: OpenPath local web viewer can ONLY bind to 127.0.0.1 or localhost (attempted: {host})."
        )

    handler_cls = type(
        "ConfiguredLocalViewerHandler",
        (LocalViewerHandler,),
        {"config": config, "repo": Repository(DatabaseManager(config.db_path))},
    )

    server = HTTPServer((host, port), handler_cls)
    print(f"\n✓ OpenPath Local Web Viewer running at http://{host}:{port}/")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
