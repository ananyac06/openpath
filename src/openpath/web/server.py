"""Local-only read-only web server for inspecting research results, live opportunities, and the 1,000+ verified organizations directory."""

from __future__ import annotations

import html
import logging
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from openpath.config import Config
from openpath.db.connection import DatabaseManager
from openpath.db.repository import Repository
from openpath.models.entities import WorkMode
from openpath.taxonomy import (
    CAREER_STAGE_LABELS,
    FUNCTION_AREA_LABELS,
    CareerStage,
    ClassifiedOpportunity,
    FunctionArea,
    classify_opportunity,
)

logger = logging.getLogger(__name__)

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

STAGE_ORDER: list[CareerStage] = [
    CareerStage.INTERNSHIP,
    CareerStage.NEW_GRAD,
    CareerStage.ENTRY,
    CareerStage.PROFESSIONAL,
    CareerStage.LEADERSHIP,
    CareerStage.UNSPECIFIED,
]

STAGE_ICONS = {
    CareerStage.INTERNSHIP: "🎓",
    CareerStage.NEW_GRAD: "🎯",
    CareerStage.ENTRY: "🌱",
    CareerStage.PROFESSIONAL: "💼",
    CareerStage.LEADERSHIP: "🧭",
    CareerStage.UNSPECIFIED: "❔",
}

STAGE_BLURBS = {
    CareerStage.INTERNSHIP: "Internships, traineeships and apprenticeships — a great starting point for students and early learners.",
    CareerStage.NEW_GRAD: "Roles aimed at recent graduates and campus hires.",
    CareerStage.ENTRY: "Entry-level positions (0-2 years) for those starting their careers.",
    CareerStage.PROFESSIONAL: "Experienced individual contributor and specialist roles.",
    CareerStage.LEADERSHIP: "Management, lead and executive-track positions.",
    CareerStage.UNSPECIFIED: "Listings without a clearly stated level — open the role to verify requirements before assuming fit.",
}


def safe_href(url: str | None) -> str:
    """Return an escaped http(s) URL or '#' for unsafe/empty values."""
    if not url:
        return "#"
    candidate = url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        return "#"
    return html.escape(candidate, quote=True)


def get_country_badge(country: str | None) -> str:
    """Format country with flag emoji."""
    c = (country or "").strip().lower()
    if c in {"us", "usa"} or "united states" in c:
        return "🇺🇸 United States"
    if c in {"in"} or "india" in c:
        return "🇮🇳 India"
    if c in {"uk", "gb"} or "united kingdom" in c:
        return "🇬🇧 United Kingdom"
    if "germany" in c:
        return "🇩🇪 Germany"
    if "france" in c:
        return "🇫🇷 France"
    if "canada" in c:
        return "🇨🇦 Canada"
    if "netherlands" in c:
        return "🇳🇱 Netherlands"
    if "singapore" in c:
        return "🇸🇬 Singapore"
    if "ireland" in c:
        return "🇮🇪 Ireland"
    if "sweden" in c:
        return "🇸🇪 Sweden"
    if "switzerland" in c:
        return "🇨🇭 Switzerland"
    if "japan" in c:
        return "🇯🇵 Japan"
    if "australia" in c:
        return "🇦🇺 Australia"
    if "israel" in c:
        return "🇮🇱 Israel"
    if "global" in c or "multiple" in c or "worldwide" in c:
        return "🌍 Global / Multiple"
    if country:
        return f"🌐 {html.escape(country.strip())}"
    return "🌐 Unspecified"


def get_category_label(category: str) -> str:
    """Format directory category."""
    cat = (category or "").strip().lower()
    if cat == "us_sp500":
        return "🏢 S&P 500 / US Listed"
    if cat == "indian_listed":
        return "🇮🇳 Indian Listed (BSE/NSE)"
    if cat == "tech_unicorn":
        return "🦄 Tech Unicorn / Startup"
    if cat == "open_source":
        return "🌐 Open Source Foundation"
    if cat == "research_institute":
        return "🔬 Research Institute"
    return "🏢 Enterprise"


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenPath Local Research Viewer & Verified Directory</title>
    <style>
        :root {{
            --bg: #0d1117;
            --card-bg: #161b22;
            --surface: #1c2128;
            --border: #30363d;
            --border-muted: #21262d;
            --text-main: #c9d1d9;
            --text-muted: #8b949e;
            --accent: #58a6ff;
            --green: #238636;
            --green-light: #3fb950;
            --yellow: #d29922;
            --purple: #bc8cff;
            --orange: #db6d28;
            --red: #f85149;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            margin: 0;
            padding: 18px 22px;
            line-height: 1.5;
        }}
        .container {{ max-width: 1320px; margin: 0 auto; }}
        h1 {{ color: #f0f6fc; font-size: 28px; margin: 0 0 6px; }}
        h2 {{ color: #f0f6fc; font-size: 18px; margin: 0; }}
        .subtitle {{ color: var(--text-muted); margin: 0 0 18px; font-size: 14px; }}

        .stats-bar {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
            gap: 10px;
            margin-bottom: 18px;
        }}
        .stat-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px 14px;
            cursor: pointer;
            transition: border-color 0.15s, transform 0.15s;
        }}
        .stat-card:hover {{ border-color: #484f58; transform: translateY(-1px); }}
        .stat-value {{ font-size: 22px; font-weight: 700; color: #f0f6fc; display: block; }}
        .stat-label {{ font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.4px; }}

        .view-switcher {{
            display: flex;
            gap: 10px;
            margin-bottom: 14px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 12px;
        }}
        .view-btn {{
            background: transparent;
            color: var(--text-muted);
            border: 1px solid transparent;
            padding: 9px 16px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
        }}
        .view-btn:hover {{ color: #f0f6fc; background: var(--surface); }}
        .view-btn.active {{
            color: #fff;
            background: #1f6feb;
            border-color: rgba(240,246,252,0.1);
        }}
        .view-badge {{
            background: rgba(255,255,255,0.15);
            padding: 1px 8px;
            border-radius: 999px;
            font-size: 12px;
            margin-left: 6px;
        }}

        .toolbar {{
            display: flex;
            gap: 10px;
            margin-bottom: 12px;
            flex-wrap: wrap;
            align-items: center;
        }}
        .search-form {{
            display: flex;
            gap: 8px;
            flex: 1 1 320px;
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 10px;
        }}
        .search-form input {{
            flex: 1;
            background: transparent;
            border: none;
            color: #f0f6fc;
            font-size: 14px;
            outline: none;
            min-width: 120px;
        }}
        .btn {{
            background: #21262d;
            color: var(--text-main);
            border: 1px solid var(--border);
            padding: 7px 12px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .btn:hover {{ background: #30363d; color: #fff; }}
        .btn-primary {{ background: var(--green); color: #fff; border-color: rgba(240,246,252,0.1); }}
        .btn-primary:hover {{ background: #2ea043; }}

        .filter-panel {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 14px;
        }}
        .filter-group {{ margin-bottom: 10px; }}
        .filter-group:last-child {{ margin-bottom: 0; }}
        .filter-label {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 6px;
            font-weight: 700;
        }}
        .filter-tabs {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .tab-btn {{
            background: var(--surface);
            color: var(--text-muted);
            border: 1px solid var(--border);
            padding: 6px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .tab-btn:hover {{ background: #21262d; color: #f0f6fc; }}
        .tab-btn.active {{ background: #1f6feb; color: #fff; border-color: #388bfd; }}
        .tab-count {{
            background: rgba(0,0,0,0.25);
            padding: 0 6px;
            border-radius: 999px;
            font-size: 11px;
        }}

        .stage-section {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 10px;
            margin-bottom: 14px;
            overflow: hidden;
        }}
        .stage-summary {{
            list-style: none;
            cursor: pointer;
            padding: 14px 16px;
            background: var(--surface);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            user-select: none;
        }}
        .stage-summary::-webkit-details-marker {{ display: none; }}
        .stage-left {{ display: flex; align-items: center; gap: 12px; min-width: 0; }}
        .stage-icon {{ font-size: 22px; }}
        .stage-title {{ font-size: 17px; font-weight: 700; color: #f0f6fc; margin: 0; }}
        .stage-blurb {{ font-size: 12px; color: var(--text-muted); margin: 2px 0 0; }}
        .stage-count {{
            background: #30363d;
            color: #f0f6fc;
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 12px;
            font-weight: 700;
            white-space: nowrap;
        }}
        .stage-body {{ padding: 10px 12px 12px; border-top: 1px solid var(--border-muted); }}

        .company-card {{
            background: #0f141a;
            border: 1px solid var(--border-muted);
            border-radius: 8px;
            margin-bottom: 10px;
            overflow: hidden;
        }}
        .company-summary {{
            padding: 10px 12px;
            cursor: pointer;
            list-style: none;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 10px;
            background: #161b22;
            user-select: none;
        }}
        .company-summary::-webkit-details-marker {{ display: none; }}
        .company-header-left {{ display: flex; align-items: center; gap: 10px; min-width: 0; }}
        .company-avatar {{
            width: 30px; height: 30px; border-radius: 6px; flex-shrink: 0;
            display: flex; align-items: center; justify-content: center;
            font-size: 12px; font-weight: 700; color: #fff;
        }}
        .company-title {{ font-size: 14px; font-weight: 700; color: #f0f6fc; margin: 0; }}
        .company-ticker {{ font-size: 11px; color: var(--text-muted); font-weight: 400; margin-left: 4px; }}
        .company-badges {{ display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }}
        .badge-count {{
            background: #30363d; color: #f0f6fc; border-radius: 999px;
            font-size: 11px; padding: 2px 8px; font-weight: 700;
        }}

        .opportunities-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        .opportunities-table th {{
            text-align: left; color: var(--text-muted); font-size: 11px;
            text-transform: uppercase; letter-spacing: 0.4px;
            padding: 8px 12px; background: #131920; border-bottom: 1px solid var(--border-muted);
        }}
        .opportunities-table td {{
            padding: 10px 12px; border-bottom: 1px solid var(--border-muted); vertical-align: top;
        }}
        .opportunities-table tr:last-child td {{ border-bottom: none; }}
        .opportunities-table tr:hover td {{ background: rgba(88,166,255,0.03); }}
        .role-title {{ color: #f0f6fc; font-weight: 600; margin-bottom: 4px; }}
        .role-meta {{ color: var(--text-muted); font-size: 12px; }}
        .badge {{
            display: inline-flex; align-items: center; gap: 4px;
            font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 999px;
            border: 1px solid transparent; margin: 1px 4px 1px 0; white-space: nowrap;
        }}
        .badge-internship {{ background: rgba(245,158,11,0.15); color: #fbbf24; border-color: rgba(245,158,11,0.3); }}
        .badge-entry {{ background: rgba(16,185,129,0.15); color: #34d399; border-color: rgba(16,185,129,0.3); }}
        .badge-newgrad {{ background: rgba(56,189,248,0.15); color: #7dd3fc; border-color: rgba(56,189,248,0.3); }}
        .badge-prof {{ background: rgba(88,166,255,0.12); color: #79c0ff; border-color: rgba(88,166,255,0.25); }}
        .badge-lead {{ background: rgba(188,140,255,0.15); color: #d2a8ff; border-color: rgba(188,140,255,0.3); }}
        .badge-unknown {{ background: rgba(139,148,158,0.15); color: #c9d1d9; border-color: rgba(139,148,158,0.3); }}
        .badge-remote {{ background: rgba(188,140,255,0.15); color: #d2a8ff; border-color: rgba(188,140,255,0.3); }}
        .badge-onsite {{ background: rgba(88,166,255,0.12); color: #79c0ff; border-color: rgba(88,166,255,0.25); }}
        .badge-verified {{ background: rgba(63,185,80,0.15); color: #3fb950; border-color: rgba(63,185,80,0.3); }}
        .badge-fn {{ background: rgba(219,109,40,0.12); color: #ffa657; border-color: rgba(219,109,40,0.25); }}

        .directory-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }}
        .org-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        .org-header {{ display: flex; align-items: flex-start; gap: 12px; margin-bottom: 8px; }}
        .org-title {{ font-size: 15px; font-weight: 700; color: #f0f6fc; margin: 0; }}
        .org-legal {{ font-size: 12px; color: var(--text-muted); margin: 2px 0 0; }}
        .org-meta-badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }}
        .org-footer {{
            display: flex; justify-content: space-between; align-items: center;
            margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-muted);
        }}
        .empty-state {{
            text-align: center; padding: 40px; color: var(--text-muted);
            background: var(--card-bg); border: 1px dashed var(--border); border-radius: 8px;
        }}
        .hidden {{ display: none !important; }}
        @media (max-width: 800px) {{
            body {{ padding: 12px; }}
            .stats-bar {{ grid-template-columns: repeat(2, 1fr); }}
            .directory-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>OpenPath Local Research Viewer</h1>
        <p class="subtitle">Evidence-backed opportunities organized by career stage and function — easier to scan for beginners and pros. Read-only local view (127.0.0.1 Local Only).</p>

        <div class="stats-bar">
            <div class="stat-card" onclick="switchView('directory')">
                <span class="stat-value" style="color:#58a6ff;">{total_verified_orgs}</span>
                <span class="stat-label">Verified Organizations</span>
            </div>
            <div class="stat-card" onclick="switchView('opportunities','all')">
                <span class="stat-value">{total_opportunities}</span>
                <span class="stat-label">Live Job Roles</span>
            </div>
            <div class="stat-card" onclick="switchView('opportunities','start_here')">
                <span class="stat-value" style="color:#3fb950;">{start_here_count}</span>
                <span class="stat-label">Start Here (Beginner-Friendly)</span>
            </div>
            <div class="stat-card" onclick="switchView('opportunities','remote')">
                <span class="stat-value" style="color:#bc8cff;">{remote_hybrid_count}</span>
                <span class="stat-label">Remote & Hybrid</span>
            </div>
            <div class="stat-card" onclick="switchView('opportunities','india')">
                <span class="stat-value" style="color:#f59e0b;">{india_count}</span>
                <span class="stat-label">India-Mentioned Listings</span>
            </div>
        </div>

        <div class="view-switcher">
            <button type="button" id="btnViewOpportunities" class="view-btn active" onclick="switchView('opportunities')">💼 Live Opportunities <span class="view-badge">{total_opportunities}</span></button>
            <button type="button" id="btnViewDirectory" class="view-btn" onclick="switchView('directory')">🏛️ Verified Directory <span class="view-badge">{total_verified_orgs}</span></button>
        </div>

        <div id="sectionOpportunities">
            <div class="toolbar">
                <form action="/" method="GET" class="search-form">
                    <input type="text" id="oppSearchInput" name="q" value="{query}" placeholder="Search title, company, skills..." autocomplete="off">
                    <button type="submit" class="btn btn-primary">Search</button>
                </form>
                <a href="/" class="btn">Reset</a>
                <button type="button" class="btn" onclick="toggleAllCards()">Expand/Collapse Companies</button>
            </div>

            <div class="filter-panel">
                <div class="filter-group">
                    <div class="filter-label">Quick collections</div>
                    <div class="filter-tabs" id="collectionTabs">
                        {collection_buttons}
                    </div>
                </div>
                <div class="filter-group">
                    <div class="filter-label">Function areas</div>
                    <div class="filter-tabs" id="functionTabs">
                        {function_buttons}
                    </div>
                </div>
            </div>

            <div id="stageContainer">
                {stage_sections}
            </div>
        </div>

        <div id="sectionDirectory" style="display:none;">
            <div class="toolbar">
                <div class="search-form" style="max-width:520px;">
                    <input type="text" id="dirSearchInput" placeholder="Search organizations by name, ticker, country..." autocomplete="off">
                </div>
                <span style="color:var(--text-muted); font-size:13px;">Showing <strong id="directoryVisibleCount">{total_verified_orgs}</strong> organizations</span>
            </div>
            <div class="filter-panel">
                <div class="filter-group">
                    <div class="filter-label">Organization categories</div>
                    <div class="filter-tabs">
                        <button type="button" class="tab-btn active dir-filter-btn" onclick="setDirFilter('all', this)">🌟 All <span class="tab-count">{total_verified_orgs}</span></button>
                        <button type="button" class="tab-btn dir-filter-btn" onclick="setDirFilter('us_sp500', this)">🏢 S&P 500 / US <span class="tab-count">{sp500_orgs_count}</span></button>
                        <button type="button" class="tab-btn dir-filter-btn" onclick="setDirFilter('indian_listed', this)">🇮🇳 BSE/NSE <span class="tab-count">{indian_orgs_count}</span></button>
                        <button type="button" class="tab-btn dir-filter-btn" onclick="setDirFilter('tech_unicorn', this)">🦄 Unicorns <span class="tab-count">{unicorn_orgs_count}</span></button>
                        <button type="button" class="tab-btn dir-filter-btn" onclick="setDirFilter('open_source', this)">🌐 Open Source <span class="tab-count">{oss_orgs_count}</span></button>
                        <button type="button" class="tab-btn dir-filter-btn" onclick="setDirFilter('research_institute', this)">🔬 Research <span class="tab-count">{res_orgs_count}</span></button>
                    </div>
                </div>
            </div>
            <div class="directory-grid" id="directoryGrid">
                {directory_cards}
            </div>
        </div>
    </div>

    <script>
        let activeCollection = 'all';
        let activeFunction = 'all';
        let activeDirCategory = 'all';

        function switchView(viewName, collection) {{
            const secOpps = document.getElementById('sectionOpportunities');
            const secDir = document.getElementById('sectionDirectory');
            const btnOpps = document.getElementById('btnViewOpportunities');
            const btnDir = document.getElementById('btnViewDirectory');
            if (viewName === 'directory') {{
                secOpps.style.display = 'none';
                secDir.style.display = '';
                btnOpps.classList.remove('active');
                btnDir.classList.add('active');
            }} else {{
                secOpps.style.display = '';
                secDir.style.display = 'none';
                btnOpps.classList.add('active');
                btnDir.classList.remove('active');
                if (collection) {{
                    const map = {{
                        'internship': 'stage:internship',
                        'entry_level': 'stage:entry',
                        'student_friendly': 'start_here',
                        'remote': 'remote',
                        'india': 'india',
                        'all': 'all'
                    }};
                    setCollection(map[collection] || collection);
                }}
            }}
        }}

        function setCollection(id, btn) {{
            activeCollection = id || 'all';
            if (!btn) {{
                btn = document.querySelector('#collectionTabs .tab-btn[data-collection="' + CSS.escape(activeCollection) + '"]');
            }}
            document.querySelectorAll('#collectionTabs .tab-btn').forEach(b => b.classList.toggle('active', b === btn));
            applyOppFilters();
        }}

        function setFunction(id, btn) {{
            activeFunction = id || 'all';
            if (!btn) {{
                btn = document.querySelector('#functionTabs .tab-btn[data-function="' + CSS.escape(activeFunction) + '"]');
            }}
            document.querySelectorAll('#functionTabs .tab-btn').forEach(b => b.classList.toggle('active', b === btn));
            applyOppFilters();
        }}

        function toggleAllCards() {{
            const cards = document.querySelectorAll('details.company-card');
            if (!cards.length) return;
            const anyOpen = Array.from(cards).some(c => c.open);
            cards.forEach(c => c.open = !anyOpen);
        }}

        function jobMatchesCollection(row) {{
            const stage = row.dataset.stage || '';
            const wm = row.dataset.workmode || '';
            const india = row.dataset.india === '1';
            if (activeCollection === 'all') return true;
            if (activeCollection === 'start_here') return stage === 'internship' || stage === 'new_grad' || stage === 'entry';
            if (activeCollection === 'remote') return wm === 'remote' || wm === 'hybrid';
            if (activeCollection === 'india') return india;
            if (activeCollection === 'experienced') return stage === 'professional' || stage === 'leadership';
            if (activeCollection === 'level_not_stated') return stage === 'unspecified';
            if (activeCollection.startsWith('stage:')) return stage === activeCollection.slice(6);
            return true;
        }}

        function applyOppFilters() {{
            const q = (document.getElementById('oppSearchInput')?.value || '').toLowerCase().trim();
            const sections = document.querySelectorAll('.stage-section');
            sections.forEach(section => {{
                const stage = section.dataset.stage || '';
                const companies = section.querySelectorAll('.company-card');
                let sectionVisible = 0;
                companies.forEach(card => {{
                    const rows = card.querySelectorAll('tr.job-row');
                    let cardVisible = 0;
                    rows.forEach(row => {{
                        const text = row.dataset.search || '';
                        const fn = row.dataset.function || 'general';
                        const okText = !q || text.indexOf(q) !== -1;
                        const okFn = activeFunction === 'all' || fn === activeFunction;
                        const okCol = jobMatchesCollection(row);
                        const show = okText && okFn && okCol;
                        row.style.display = show ? '' : 'none';
                        if (show) cardVisible++;
                    }});
                    card.style.display = cardVisible ? '' : 'none';
                    const badge = card.querySelector('.visible-count');
                    if (badge) badge.textContent = cardVisible + ' shown';
                    if (cardVisible && (q || activeCollection !== 'all' || activeFunction !== 'all')) card.open = true;
                    if (cardVisible) sectionVisible += cardVisible;
                }});
                section.style.display = sectionVisible ? '' : 'none';
                const secCount = section.querySelector('.stage-visible-count');
                if (secCount) secCount.textContent = sectionVisible + ' roles visible';
            }});
        }}

        function setDirFilter(cat, btn) {{
            activeDirCategory = cat || 'all';
            document.querySelectorAll('.dir-filter-btn').forEach(b => b.classList.toggle('active', b === btn));
            applyDirFilters();
        }}

        function applyDirFilters() {{
            const q = (document.getElementById('dirSearchInput')?.value || '').toLowerCase().trim();
            const cards = document.querySelectorAll('.org-card');
            let visible = 0;
            cards.forEach(card => {{
                const hay = (card.dataset.name || '') + ' ' + (card.dataset.ticker || '') + ' ' + (card.dataset.country || '');
                const okText = !q || hay.indexOf(q) !== -1;
                const okCat = activeDirCategory === 'all' || (card.dataset.category || '') === activeDirCategory;
                const show = okText && okCat;
                card.style.display = show ? '' : 'none';
                if (show) visible++;
            }});
            const label = document.getElementById('directoryVisibleCount');
            if (label) label.textContent = String(visible);
        }}

        document.getElementById('oppSearchInput')?.addEventListener('input', applyOppFilters);
        document.getElementById('dirSearchInput')?.addEventListener('input', applyDirFilters);
        applyOppFilters();
    </script>
</body>
</html>
"""


def _stage_badge(stage: CareerStage) -> str:
    cls = {
        CareerStage.INTERNSHIP: "badge-internship",
        CareerStage.NEW_GRAD: "badge-newgrad",
        CareerStage.ENTRY: "badge-entry",
        CareerStage.PROFESSIONAL: "badge-prof",
        CareerStage.LEADERSHIP: "badge-lead",
        CareerStage.UNSPECIFIED: "badge-unknown",
    }.get(stage, "badge-unknown")
    return f"<span class='badge {cls}'>{html.escape(CAREER_STAGE_LABELS[stage])}</span>"


class LocalViewerHandler(BaseHTTPRequestHandler):
    config: Config
    repo: Repository

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        search_query = params.get("q", [None])[0]

        opps = self.repo.list_opportunities(search_query=search_query, limit=10000)
        all_orgs = self.repo.list_organisations(limit=5000)

        classified = [classify_opportunity(o) for o in opps]

        # Counts for collections
        start_here_stages = {CareerStage.INTERNSHIP, CareerStage.NEW_GRAD, CareerStage.ENTRY}
        start_here_count = sum(1 for c in classified if c.classification.stage in start_here_stages)
        remote_hybrid_count = sum(
            1 for c in classified if c.opportunity.work_mode in (WorkMode.REMOTE, WorkMode.HYBRID)
        )
        india_count = sum(1 for c in classified if c.india_eligible)

        stage_counts: dict[CareerStage, int] = defaultdict(int)
        function_counts: dict[FunctionArea, int] = defaultdict(int)
        for c in classified:
            stage_counts[c.classification.stage] += 1
            function_counts[c.classification.function] += 1

        # Group by stage -> company
        by_stage: dict[CareerStage, dict[str, list[ClassifiedOpportunity]]] = {
            s: defaultdict(list) for s in STAGE_ORDER
        }
        for c in classified:
            by_stage[c.classification.stage][c.opportunity.company_name].append(c)

        stage_sections: list[str] = []
        for stage in STAGE_ORDER:
            companies = by_stage[stage]
            stage_total = stage_counts.get(stage, 0)
            if stage_total == 0:
                continue
            company_blocks: list[str] = []
            for company_name, items in sorted(companies.items(), key=lambda x: (-len(x[1]), x[0].lower())):
                rows: list[str] = []
                remote_n = hybrid_n = onsite_n = 0
                for item in sorted(items, key=lambda x: (x.opportunity.title or "").lower()):
                    o = item.opportunity
                    cls = item.classification
                    wm = o.work_mode.value if o.work_mode else "unclear"
                    if o.work_mode == WorkMode.REMOTE:
                        remote_n += 1
                        wm_badge = "<span class='badge badge-remote'>🌐 Remote</span>"
                    elif o.work_mode == WorkMode.HYBRID:
                        hybrid_n += 1
                        wm_badge = "<span class='badge badge-remote'>🔀 Hybrid</span>"
                    elif o.work_mode == WorkMode.ONSITE:
                        onsite_n += 1
                        wm_badge = "<span class='badge badge-onsite'>🏢 Onsite</span>"
                    else:
                        wm_badge = "<span class='badge badge-unknown'>Work mode: not stated</span>"

                    loc = o.location_raw or "Location not disclosed"
                    fn_label = FUNCTION_AREA_LABELS[cls.function]
                    india_flag = "1" if item.india_eligible else "0"
                    search_blob = " ".join(
                        [
                            o.title or "",
                            company_name,
                            loc,
                            " ".join(o.locations or []),
                            o.compensation_raw or "",
                            CAREER_STAGE_LABELS[cls.stage],
                            fn_label,
                        ]
                    ).lower()
                    apply_href = safe_href(o.canonical_application_url)
                    rows.append(
                        "<tr class='job-row' "
                        f"data-stage='{html.escape(stage.value)}' "
                        f"data-function='{html.escape(cls.function.value)}' "
                        f"data-workmode='{html.escape(wm)}' "
                        f"data-india='{india_flag}' "
                        f"data-search='{html.escape(search_blob, quote=True)}'>"
                        "<td>"
                        f"<div class='role-title'>{html.escape(o.title or 'Untitled role')}</div>"
                        f"<div class='role-meta'>{html.escape(loc)}</div>"
                        f"<div style='margin-top:4px;'>{_stage_badge(stage)}"
                        f"<span class='badge badge-fn'>{html.escape(fn_label)}</span>"
                        f"{wm_badge}"
                        f"{'<span class=\'badge badge-verified\'>Verified</span>' if o.admission_class == 'VERIFIED' else ''}"
                        f"</div>"
                        "</td>"
                        f"<td>{html.escape(o.compensation_raw or 'Not disclosed')}</td>"
                        "<td style='text-align:right;'>"
                        f"<a href='{apply_href}' target='_blank' rel='noopener noreferrer' class='btn btn-primary'>Apply ↗</a>"
                        "</td>"
                        "</tr>"
                    )

                meta = COMPANY_METADATA.get(company_name, {})
                ticker = meta.get("ticker", "Declared source")
                initial = meta.get("avatar") or (company_name[:2].upper() if company_name else "OP")
                avatar_color = meta.get("color") or "#238636"
                mode_bits = []
                if remote_n:
                    mode_bits.append(f"<span class='badge badge-remote'>{remote_n} remote</span>")
                if hybrid_n:
                    mode_bits.append(f"<span class='badge badge-remote'>{hybrid_n} hybrid</span>")
                if onsite_n:
                    mode_bits.append(f"<span class='badge badge-onsite'>{onsite_n} onsite</span>")
                company_open = " open" if len(items) <= 4 and stage in start_here_stages else ""
                company_blocks.append(
                    f"<details class='company-card'{company_open} data-company='{html.escape(company_name, quote=True)}'>"
                    "<summary class='company-summary'>"
                    "<div class='company-header-left'>"
                    f"<div class='company-avatar' style='background:{avatar_color};'>{html.escape(initial)}</div>"
                    "<div>"
                    f"<div class='company-title'>{html.escape(company_name)} <span class='company-ticker'>({html.escape(ticker)})</span></div>"
                    f"<div class='role-meta'>{len(items)} role{'s' if len(items) != 1 else ''} · <span class='visible-count'>{len(items)} shown</span></div>"
                    "</div></div>"
                    f"<div class='company-badges'><span class='badge-count'>{len(items)}</span> {' '.join(mode_bits)}</div>"
                    "</summary>"
                    "<table class='opportunities-table'><thead><tr>"
                    "<th style='width:60%;'>Role</th><th style='width:25%;'>Compensation</th><th style='width:15%; text-align:right;'>Action</th>"
                    "</tr></thead><tbody>"
                    + "".join(rows)
                    + "</tbody></table></details>"
                )

            section_open = " open" if stage in start_here_stages or stage_total <= 25 else ""
            stage_sections.append(
                f"<details class='stage-section'{section_open} data-stage='{html.escape(stage.value)}'>"
                "<summary class='stage-summary'>"
                "<div class='stage-left'>"
                f"<div class='stage-icon'>{STAGE_ICONS[stage]}</div>"
                "<div>"
                f"<div class='stage-title'>{STAGE_ICONS[stage]} {html.escape(CAREER_STAGE_LABELS[stage])}</div>"
                f"<div class='stage-blurb'>{html.escape(STAGE_BLURBS[stage])}</div>"
                "</div></div>"
                "<div style='text-align:right;'>"
                f"<div class='stage-count'>{stage_total} roles</div>"
                f"<div class='role-meta stage-visible-count' style='margin-top:4px;'>{stage_total} roles visible</div>"
                "</div></summary>"
                f"<div class='stage-body'>{''.join(company_blocks) if company_blocks else '<div class=\'empty-state\'>No roles in this section.</div>'}</div>"
                "</details>"
            )

        if not stage_sections:
            stage_sections.append(
                "<div class='empty-state'><strong>No opportunities found.</strong><br>Try clearing the search or run discovery/ingestion to populate local results.</div>"
            )

        # Collection buttons
        collection_defs = [
            ("all", "🌟 All", len(classified)),
            ("start_here", "🚀 Start Here", start_here_count),
            ("stage:internship", "🎓 Internships", stage_counts.get(CareerStage.INTERNSHIP, 0)),
            ("stage:new_grad", "🎯 New Grad", stage_counts.get(CareerStage.NEW_GRAD, 0)),
            ("stage:entry", "🌱 Entry Level", stage_counts.get(CareerStage.ENTRY, 0)),
            ("experienced", "💼 Experienced", stage_counts.get(CareerStage.PROFESSIONAL, 0) + stage_counts.get(CareerStage.LEADERSHIP, 0)),
            ("level_not_stated", "❔ Level Not Stated", stage_counts.get(CareerStage.UNSPECIFIED, 0)),
            ("remote", "🌐 Remote/Hybrid", remote_hybrid_count),
            ("india", "🇮🇳 India-mentioned", india_count),
        ]
        collection_buttons = []
        for cid, label, count in collection_defs:
            active = " active" if cid == "all" else ""
            collection_buttons.append(
                f"<button type='button' class='tab-btn{active}' data-collection='{html.escape(cid, quote=True)}' onclick='setCollection(\"{html.escape(cid, quote=True)}\", this)'>{label} <span class='tab-count'>{count}</span></button>"
            )

        # Function buttons
        function_buttons = [
            f"<button type='button' class='tab-btn active' data-function='all' onclick='setFunction(\"all\", this)'>All functions <span class='tab-count'>{len(classified)}</span></button>"
        ]
        for fn in FunctionArea:
            cnt = function_counts.get(fn, 0)
            if cnt == 0:
                continue
            function_buttons.append(
                f"<button type='button' class='tab-btn' data-function='{html.escape(fn.value, quote=True)}' onclick='setFunction(\"{html.escape(fn.value, quote=True)}\", this)'>{html.escape(FUNCTION_AREA_LABELS[fn])} <span class='tab-count'>{cnt}</span></button>"
            )

        # Directory
        directory_cards: list[str] = []
        sp500_orgs_count = indian_orgs_count = unicorn_orgs_count = oss_orgs_count = res_orgs_count = 0
        avatar_palette = ["#238636", "#1f6feb", "#8957e5", "#da3633", "#d29922", "#00d09c", "#f38020", "#3ecf8e"]
        for idx, org in enumerate(all_orgs):
            cat = (org.get("category") or "").strip()
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

            cname = org.get("canonical_name") or "Unknown"
            lname = org.get("legal_name") or ""
            initial = cname[:2].upper() if len(cname) >= 2 else "OP"
            av_color = avatar_palette[idx % len(avatar_palette)]
            country_badge = get_country_badge(org.get("country") or "")
            category_badge = get_category_label(cat)
            live_jobs = int(org.get("live_jobs_count") or 0)
            live_jobs_html = ""
            if live_jobs > 0:
                live_jobs_html = (
                    f"<span class='badge badge-verified' style='cursor:pointer;' onclick=\"switchView('opportunities'); document.getElementById('oppSearchInput').value={html.escape(repr(cname), quote=True)}; applyOppFilters();\">{live_jobs} Live Jobs</span>"
                )
            careers_href = safe_href(org.get("careers_url"))
            reg_href = safe_href(org.get("registry_url"))
            directory_cards.append(
                f"<div class='org-card' data-category='{html.escape(cat, quote=True)}' data-name='{html.escape(cname.lower(), quote=True)}' "
                f"data-ticker='{html.escape(str(org.get('registry_id') or '').lower(), quote=True)}' data-country='{html.escape(str(org.get('country') or '').lower(), quote=True)}'>"
                "<div>"
                "<div class='org-header'>"
                f"<div class='company-avatar' style='background:{av_color};'>{html.escape(initial)}</div>"
                f"<div><div class='org-title'>{html.escape(cname)}</div><div class='org-legal'>{html.escape(lname)}</div></div>"
                "</div>"
                "<div class='org-meta-badges'>"
                f"<span class='badge badge-onsite'>{country_badge}</span>"
                f"<span class='badge badge-fn'>{category_badge}</span>"
                "</div></div>"
                "<div class='org-footer'>"
                f"<div>{live_jobs_html}</div>"
                "<div class='org-actions'>"
                f"<a href='{careers_href}' target='_blank' rel='noopener noreferrer' class='btn btn-primary'>Careers ↗</a>"
                f"<a href='{reg_href}' target='_blank' rel='noopener noreferrer' class='btn'>Registry</a>"
                "</div></div></div>"
            )

        body = HTML_TEMPLATE.format(
            total_verified_orgs=len(all_orgs),
            total_opportunities=len(classified),
            start_here_count=start_here_count,
            remote_hybrid_count=remote_hybrid_count,
            india_count=india_count,
            sp500_orgs_count=sp500_orgs_count,
            indian_orgs_count=indian_orgs_count,
            unicorn_orgs_count=unicorn_orgs_count,
            oss_orgs_count=oss_orgs_count,
            res_orgs_count=res_orgs_count,
            query=html.escape(search_query or "", quote=True),
            collection_buttons="".join(collection_buttons),
            function_buttons="".join(function_buttons),
            stage_sections="".join(stage_sections),
            directory_cards="".join(directory_cards) if directory_cards else "<div class='empty-state'>No verified organizations found.</div>",
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        logger.info("127.0.0.1 - - [%s] %s", self.log_date_time_string(), format % args)


def run_server(config: Config, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Launch the local HTTP server bound explicitly to 127.0.0.1."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError(
            "Security violation: OpenPath local web viewer can ONLY bind to 127.0.0.1"
        )

    handler_cls = type(
        "ConfiguredLocalViewerHandler",
        (LocalViewerHandler,),
        {"config": config, "repo": Repository(DatabaseManager(config.db_path))},
    )

    server = HTTPServer((host, port), handler_cls)
    print(f"\n  OpenPath Research Viewer running at http://{host}:{port}")
    print("  Browse live opportunities and 1,000+ verified organizations.")
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
    finally:
        server.server_close()
