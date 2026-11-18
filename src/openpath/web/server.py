"""Local-only read-only web server for inspecting research results, live opportunities, and the 1,000+ verified organizations directory."""

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

INTERN_REGEX = re.compile(
    r"\b(intern|internship|summer|winter|trainee|apprentice|co-op)\b", re.IGNORECASE
)
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
        "category": "tech_unicorn",
        "avatar": "SB",
        "color": "#3ecf8e",
    },
    "Meesho": {
        "ticker": "Top Indian E-Commerce Unicorn (Bengaluru)",
        "category": "tech_unicorn",
        "avatar": "ME",
        "color": "#f43397",
    },
    "CRED": {
        "ticker": "Top Indian Fintech Unicorn (Bengaluru)",
        "category": "tech_unicorn",
        "avatar": "CR",
        "color": "#212529",
    },
    "Groww": {
        "ticker": "BSE/NSE Registered Indian Wealthtech Leader",
        "category": "indian_listed",
        "avatar": "GW",
        "color": "#00d09c",
    },
    "PostHog": {
        "ticker": "Open Source Product Analytics Platform",
        "category": "tech_unicorn",
        "avatar": "PH",
        "color": "#ffd000",
    },
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenPath Local Research Viewer & Verified Directory</title>
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
        .container { max-width: 1360px; margin: 0 auto; }
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
            cursor: pointer;
            transition: border-color 0.15s, transform 0.15s;
        }
        .stat-card:hover { border-color: #58a6ff; transform: translateY(-1px); }
        .stat-value { font-size: 22px; font-weight: bold; color: #f0f6fc; }
        .stat-label { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

        /* Primary View Switcher Tabs */
        .view-switcher {
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 12px;
        }
        .view-btn {
            background: #161b22;
            color: var(--text-muted);
            border: 1px solid var(--border);
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 700;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        .view-btn:hover { background: #21262d; color: #f0f6fc; border-color: #484f58; }
        .view-btn.active {
            background: var(--accent);
            color: #0d1117;
            border-color: var(--accent);
        }
        .view-badge {
            background: rgba(255, 255, 255, 0.15);
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
        }
        .view-btn.active .view-badge {
            background: rgba(0, 0, 0, 0.25);
            color: #0d1117;
        }

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

        /* Grouped Company Cards (Opportunities View) */
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
        .badge-hot {
            background: rgba(239, 68, 68, 0.15);
            color: #ef4444;
            border: 1px solid rgba(239, 68, 68, 0.4);
            font-weight: 700;
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

        /* Verified Organizations Directory Grid */
        .directory-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
            gap: 14px;
            margin-bottom: 30px;
        }
        .org-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: border-color 0.2s, transform 0.2s;
        }
        .org-card:hover {
            border-color: #58a6ff;
            transform: translateY(-2px);
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        }
        .org-header {
            display: flex;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 10px;
        }
        .org-title {
            font-size: 16px;
            font-weight: 700;
            color: #f0f6fc;
            margin: 0;
            line-height: 1.3;
        }
        .org-legal {
            font-size: 12px;
            color: var(--text-muted);
            margin: 2px 0 0;
        }
        .org-meta-badges {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin: 10px 0;
            font-size: 12px;
        }
        .org-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px solid var(--border-muted);
        }
        .org-actions {
            display: flex;
            gap: 8px;
            align-items: center;
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
                <h1>OpenPath Research Console & Verified Directory</h1>
                <p style="margin: 4px 0 0; color: #8b949e; font-size: 13px;">Local-first • India-first • Evidence-driven Verified Research Engine</p>
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
                    Looking for your first tech internship, open-source project, or beginner learning role?
                    Switch to <strong>💼 Live Ingested Roles</strong> to explore over 2,100 active roles with dedicated <strong>🎓 Internships</strong> and <strong>🌱 Zero-Exp</strong> filters.
                    Or explore the <strong>🏛️ Verified Directory</strong> below to browse 1,120+ authentic corporate career portals across S&P 500 tech leaders, BSE & NSE giants, and unicorns!
                </p>
            </div>
        </div>

        <!-- Stats Overview -->
        <div class="stats-bar">
            <div class="stat-card" onclick="switchView('directory')">
                <span class="stat-value" style="color: #58a6ff;">{total_verified_orgs}</span>
                <span class="stat-label">Verified Organizations Directory</span>
            </div>
            <div class="stat-card" onclick="switchView('opportunities')">
                <span class="stat-value">{total_opportunities}</span>
                <span class="stat-label">Live Ingested Job Roles</span>
            </div>
            <div class="stat-card" onclick="switchView('opportunities', 'internship')">
                <span class="stat-value" style="color: #f59e0b;">{internship_count}</span>
                <span class="stat-label">Internships & Apprenticeships</span>
            </div>
            <div class="stat-card" onclick="switchView('opportunities', 'entry_level')">
                <span class="stat-value" style="color: #10b981;">{entry_count}</span>
                <span class="stat-label">Zero-Exp & Entry-Level Roles</span>
            </div>
            <div class="stat-card" onclick="switchView('opportunities', 'remote')">
                <span class="stat-value" style="color: #bc8cff;">{remote_count}</span>
                <span class="stat-label">Remote & Hybrid Positions</span>
            </div>
        </div>

        <!-- Primary View Switcher -->
        <div class="view-switcher">
            <button type="button" id="btnViewOpportunities" class="view-btn active" onclick="switchView('opportunities')">
                💼 Live Ingested Roles <span class="view-badge">{total_opportunities}</span>
            </button>
            <button type="button" id="btnViewDirectory" class="view-btn" onclick="switchView('directory')">
                🏛️ Verified Organizations Directory <span class="view-badge">{total_verified_orgs}</span>
            </button>
        </div>

        <!-- ================= VIEW 1: LIVE OPPORTUNITIES ================= -->
        <div id="sectionOpportunities">
            <!-- Filter Chips / Tabs for Opportunities -->
            <div class="filter-tabs">
                <button type="button" class="tab-btn active opp-filter-btn" onclick="setOppFilter('all', this)">
                    🌟 All Opportunities <span class="tab-count">{total_opportunities}</span>
                </button>
                <button type="button" class="tab-btn opp-filter-btn" onclick="setOppFilter('internship', this)">
                    🎓 Internships & Trainees <span class="tab-count">{internship_count}</span>
                </button>
                <button type="button" class="tab-btn opp-filter-btn" onclick="setOppFilter('entry_level', this)">
                    🌱 Zero-Exp & Entry-Level <span class="tab-count">{entry_count}</span>
                </button>
                <button type="button" class="tab-btn opp-filter-btn" onclick="setOppFilter('student_friendly', this)">
                    🚀 Student & 0-Exp Combined <span class="tab-count">{student_friendly_count}</span>
                </button>
                <button type="button" class="tab-btn opp-filter-btn" onclick="setOppFilter('remote', this)">
                    🌐 Remote & Hybrid <span class="tab-count">{remote_count}</span>
                </button>
                <button type="button" class="tab-btn opp-filter-btn" onclick="setOppFilter('us_sp500', this)">
                    🏢 S&P 500 / US Listed <span class="tab-count">{sp500_opps_count}</span>
                </button>
                <button type="button" class="tab-btn opp-filter-btn" onclick="setOppFilter('indian_tech', this)">
                    🇮🇳 Indian Tech & Unicorns <span class="tab-count">{indian_tech_opps_count}</span>
                </button>
            </div>

            <!-- Controls Toolbar -->
            <div class="toolbar">
                <div class="search-box">
                    <input type="text" id="oppSearchInput" value="{query}" placeholder="Search opportunities by title, company, skills, or location...">
                </div>
                <button type="button" class="btn" onclick="toggleAllCards()">Toggle All</button>
            </div>

            <!-- Company Cards List -->
            <div id="companyList">
                {cards}
            </div>
        </div>

        <!-- ================= VIEW 2: VERIFIED ORGANIZATIONS DIRECTORY ================= -->
        <div id="sectionDirectory" style="display: none;">
            <!-- Category Filter Tabs for Directory -->
            <div class="filter-tabs">
                <button type="button" class="tab-btn active dir-filter-btn" onclick="setDirFilter('all', this)">
                    🌟 All Verified Organizations <span class="tab-count">{total_verified_orgs}</span>
                </button>
                <button type="button" class="tab-btn dir-filter-btn" onclick="setDirFilter('us_sp500', this)">
                    🏢 S&P 500 & US Public Leaders <span class="tab-count">{sp500_orgs_count}</span>
                </button>
                <button type="button" class="tab-btn dir-filter-btn" onclick="setDirFilter('indian_listed', this)">
                    🇮🇳 BSE & NSE Listed Indian Giants <span class="tab-count">{indian_orgs_count}</span>
                </button>
                <button type="button" class="tab-btn dir-filter-btn" onclick="setDirFilter('tech_unicorn', this)">
                    🦄 Top Tech Unicorns & Startups <span class="tab-count">{unicorn_orgs_count}</span>
                </button>
                <button type="button" class="tab-btn dir-filter-btn" onclick="setDirFilter('open_source', this)">
                    🌐 Open Source Foundations <span class="tab-count">{oss_orgs_count}</span>
                </button>
                <button type="button" class="tab-btn dir-filter-btn" onclick="setDirFilter('research_institute', this)">
                    🔬 Premier Research Institutes <span class="tab-count">{res_orgs_count}</span>
                </button>
            </div>

            <!-- Controls Toolbar for Directory -->
            <div class="toolbar">
                <div class="search-box">
                    <input type="text" id="dirSearchInput" placeholder="Search 1,120+ organizations by name, ticker, exchange, country, or jurisdiction...">
                </div>
                <span id="dirResultCount" class="badge badge-verified" style="font-size: 13px; padding: 6px 12px;">{total_verified_orgs} organizations</span>
            </div>

            <!-- Directory Grid -->
            <div id="directoryGrid" class="directory-grid">
                {directory_cards}
            </div>
        </div>
    </div>

    <script>
        let currentOppCategory = 'all';
        let currentDirCategory = 'all';

        function switchView(viewName, filterVal) {
            const secOpps = document.getElementById('sectionOpportunities');
            const secDir = document.getElementById('sectionDirectory');
            const btnOpps = document.getElementById('btnViewOpportunities');
            const btnDir = document.getElementById('btnViewDirectory');

            if (viewName === 'opportunities') {
                secOpps.style.display = '';
                secDir.style.display = 'none';
                btnOpps.classList.add('active');
                btnDir.classList.remove('active');
                if (filterVal) {
                    const btn = Array.from(document.querySelectorAll('.opp-filter-btn')).find(b => b.getAttribute('onclick')?.includes(filterVal));
                    setOppFilter(filterVal, btn);
                }
            } else {
                secOpps.style.display = 'none';
                secDir.style.display = '';
                btnOpps.classList.remove('active');
                btnDir.classList.add('active');
                if (filterVal) {
                    const btn = Array.from(document.querySelectorAll('.dir-filter-btn')).find(b => b.getAttribute('onclick')?.includes(filterVal));
                    setDirFilter(filterVal, btn);
                }
            }
        }

        function setOppFilter(cat, btn) {
            currentOppCategory = cat;
            document.querySelectorAll('.opp-filter-btn').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');
            applyOppFilters();
        }

        function setDirFilter(cat, btn) {
            currentDirCategory = cat;
            document.querySelectorAll('.dir-filter-btn').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');
            applyDirFilters();
        }

        function toggleAllCards() {
            const cards = document.querySelectorAll('details.company-card');
            if (!cards.length) return;
            const anyOpen = Array.from(cards).some(c => c.open);
            cards.forEach(c => c.open = !anyOpen);
        }

        function filterOppCompany(companyName) {
            switchView('opportunities');
            const input = document.getElementById('oppSearchInput');
            input.value = companyName;
            applyOppFilters();
            window.scrollTo({ top: 300, behavior: 'smooth' });
        }

        function applyOppFilters() {
            const searchVal = document.getElementById('oppSearchInput').value.toLowerCase().trim();
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
                    if (currentOppCategory === 'all') {
                        matchesCategory = true;
                    } else if (currentOppCategory === 'internship') {
                        matchesCategory = (rowRoleType === 'internship');
                    } else if (currentOppCategory === 'entry_level') {
                        matchesCategory = (rowRoleType === 'entry_level');
                    } else if (currentOppCategory === 'student_friendly') {
                        matchesCategory = (rowRoleType === 'internship' || rowRoleType === 'entry_level' || rowRoleType === 'fellowship');
                    } else if (currentOppCategory === 'remote') {
                        matchesCategory = (rowWorkMode === 'remote' || rowWorkMode === 'hybrid');
                    } else if (currentOppCategory === 'us_sp500') {
                        matchesCategory = (companyCat === 'us_sp500');
                    } else if (currentOppCategory === 'indian_tech') {
                        matchesCategory = (companyCat === 'indian_tech' || companyCat === 'indian_listed');
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
                    if (currentOppCategory !== 'all' || searchVal) {
                        card.open = true;
                    }
                } else {
                    card.style.display = 'none';
                }
            });
        }

        function applyDirFilters() {
            const searchVal = document.getElementById('dirSearchInput').value.toLowerCase().trim();
            const cards = document.querySelectorAll('.org-card');
            let visibleCount = 0;

            cards.forEach(card => {
                const name = (card.getAttribute('data-name') || '').toLowerCase();
                const ticker = (card.getAttribute('data-ticker') || '').toLowerCase();
                const country = (card.getAttribute('data-country') || '').toLowerCase();
                const cat = card.getAttribute('data-category') || '';

                const matchesText = !searchVal || name.includes(searchVal) || ticker.includes(searchVal) || country.includes(searchVal);
                const matchesCat = (currentDirCategory === 'all' || cat === currentDirCategory);

                if (matchesText && matchesCat) {
                    card.style.display = '';
                    visibleCount++;
                } else {
                    card.style.display = 'none';
                }
            });

            const countBadge = document.getElementById('dirResultCount');
            if (countBadge) {
                countBadge.innerText = `${visibleCount} organizations`;
            }
        }

        // Fast Client-Side Real-Time Filters
        document.getElementById('oppSearchInput')?.addEventListener('input', applyOppFilters);
        document.getElementById('dirSearchInput')?.addEventListener('input', applyDirFilters);
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


def get_country_badge(country: str) -> str:
    """Format country with flag emoji."""
    c = country.strip().lower()
    if "united states" in c or c == "us":
        return "🇺🇸 United States"
    elif "india" in c or c == "in":
        return "🇮🇳 India"
    elif "united kingdom" in c or c == "uk":
        return "🇬🇧 United Kingdom"
    elif "germany" in c:
        return "🇩🇪 Germany"
    elif "france" in c:
        return "🇫🇷 France"
    elif "japan" in c:
        return "🇯🇵 Japan"
    elif "singapore" in c:
        return "🇸🇬 Singapore"
    elif "canada" in c:
        return "🇨🇦 Canada"
    elif "switzerland" in c:
        return "🇨🇭 Switzerland"
    elif "netherlands" in c:
        return "🇳🇱 Netherlands"
    else:
        return f"🌐 {country}"


def get_category_label(category: str) -> str:
    """Return user-friendly category name."""
    mapping = {
        "us_sp500": "🏢 S&P 500 / US Listed",
        "indian_listed": "🇮🇳 BSE / NSE Listed",
        "tech_unicorn": "🦄 Tech Unicorn",
        "open_source": "🌐 Open Source Foundation",
        "research_institute": "🔬 Research Institute",
    }
    return mapping.get(category, "🏢 Verified Organization")


class LocalViewerHandler(BaseHTTPRequestHandler):
    config: Config
    repo: Repository

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        search_query = params.get("q", [None])[0]

        opps = self.repo.list_opportunities(search_query=search_query, limit=10000)
        all_orgs = self.repo.list_organisations(limit=5000)

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
        sp500_opps_count = 0
        indian_tech_opps_count = 0

        # Build Opportunities Cards (grouped by company)
        for company_name, company_opps in sorted(
            grouped.items(), key=lambda x: len(x[1]), reverse=True
        ):
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
                    sp500_opps_count += 1
                elif category in ("indian_tech", "indian_listed"):
                    indian_tech_opps_count += 1

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

        cards_output = (
            "\n".join(cards_html)
            if cards_html
            else "<div class='empty-state'><h3>No opportunities found</h3><p>Try refining your search keyword or run new source discovery.</p></div>"
        )

        # Build Directory Cards (all 1,120+ verified organizations)
        dir_cards_html: list[str] = []
        sp500_orgs_count = 0
        indian_orgs_count = 0
        unicorn_orgs_count = 0
        oss_orgs_count = 0
        res_orgs_count = 0

        # Colors palette for directory avatars
        avatar_palette = [
            "#238636",
            "#1f6feb",
            "#8957e5",
            "#da3633",
            "#d29922",
            "#00d09c",
            "#f38020",
            "#3ecf8e",
        ]

        for idx, org in enumerate(all_orgs):
            cat = org["category"]
            if cat == "us_sp500":
                sp500_orgs_count += 1
            elif cat == "indian_listed":
                indian_orgs_count += 1
            elif cat == "tech_unicorn":
                unicorn_orgs_count += 1
            elif cat == "open_source":
                oss_orgs_count += 1
            elif cat == "research_institute":
                res_orgs_count += 1

            cname = org["canonical_name"]
            lname = org["legal_name"]
            initial = cname[:2].upper() if len(cname) >= 2 else "OP"
            av_color = avatar_palette[idx % len(avatar_palette)]
            country_badge = get_country_badge(org["country"])
            category_badge = get_category_label(cat)
            live_jobs = org["live_jobs_count"]

            live_jobs_badge = ""
            if live_jobs > 0:
                live_jobs_badge = (
                    f"<button type='button' class='badge badge-hot' style='cursor:pointer;' onclick='filterOppCompany(\"{html.escape(cname)}\")'>"
                    f"🔥 {live_jobs} Live Roles"
                    f"</button>"
                )

            dir_cards_html.append(
                f"<div class='org-card' data-category='{html.escape(cat)}' data-name='{html.escape(cname.lower())}' data-ticker='{html.escape(org['registry_id'].lower())}' data-country='{html.escape(org['country'].lower())}'>\n"
                f"  <div>\n"
                f"    <div class='org-header'>\n"
                f"      <div class='company-avatar' style='background: {av_color};'>{initial}</div>\n"
                f"      <div style='flex:1;'>\n"
                f"        <h3 class='org-title'>{html.escape(cname)}</h3>\n"
                f"        <p class='org-legal'>{html.escape(lname)}</p>\n"
                f"      </div>\n"
                f"      <span class='badge badge-verified'>✓ PASS</span>\n"
                f"    </div>\n"
                f"    <div class='org-meta-badges'>\n"
                f"      <span class='badge badge-onsite'>{html.escape(country_badge)}</span>\n"
                f"      <span class='badge badge-onsite' style='color:#58a6ff;'>{html.escape(category_badge)}</span>\n"
                f"      <span class='badge badge-onsite' style='color:#e3b341;'>{html.escape(org['registry_id'])}</span>\n"
                f"    </div>\n"
                f"  </div>\n"
                f"  <div class='org-footer'>\n"
                f"    <div>{live_jobs_badge}</div>\n"
                f"    <div class='org-actions'>\n"
                f"      <a class='btn-apply' href='{html.escape(org['website_url'])}' target='_blank' rel='noopener noreferrer'>Careers Portal ↗</a>\n"
                f"    </div>\n"
                f"  </div>\n"
                f"</div>"
            )

        directory_output = "\n".join(dir_cards_html)

        body = (
            HTML_TEMPLATE.replace("{total_verified_orgs}", f"{len(all_orgs):,}")
            .replace("{total_opportunities}", f"{len(opps):,}")
            .replace("{verified_count}", f"{verified_count:,}")
            .replace("{internship_count}", str(internship_count))
            .replace("{entry_count}", str(entry_count))
            .replace("{student_friendly_count}", str(student_friendly_count))
            .replace("{remote_count}", str(remote_count))
            .replace("{sp500_opps_count}", str(sp500_opps_count))
            .replace("{indian_tech_opps_count}", str(indian_tech_opps_count))
            .replace("{sp500_orgs_count}", str(sp500_orgs_count))
            .replace("{indian_orgs_count}", str(indian_orgs_count))
            .replace("{unicorn_orgs_count}", str(unicorn_orgs_count))
            .replace("{oss_orgs_count}", str(oss_orgs_count))
            .replace("{res_orgs_count}", str(res_orgs_count))
            .replace("{query}", html.escape(search_query or ""))
            .replace("{cards}", cards_output)
            .replace("{directory_cards}", directory_output)
            .encode("utf-8")
        )

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        logger.info(
            "%s - - [%s] %s\n", self.address_string(), self.log_date_time_string(), format % args
        )


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
