"""Local-only read-only web server for inspecting research results and evidence in a browser."""

from __future__ import annotations

import html
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from openpath.config import Config
from openpath.db.connection import DatabaseManager
from openpath.db.repository import Repository
from openpath.models.entities import Opportunity

logger = logging.getLogger(__name__)

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
        .container { max-width: 1200px; margin: 0 auto; }
        header {
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 24px;
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
        /* Stats Bar */
        .stats-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            display: flex;
            flex-direction: column;
        }
        .stat-value { font-size: 24px; font-weight: bold; color: #f0f6fc; }
        .stat-label { font-size: 13px; color: var(--text-muted); margin-top: 4px; }

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
        }
        .btn:hover { background: #30363d; color: #fff; }
        .btn-primary { background: var(--green); border-color: rgba(240, 246, 252, 0.1); color: #fff; }
        .btn-primary:hover { background: #2ea043; }

        /* Grouped Company Cards */
        .company-card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            margin-bottom: 16px;
            overflow: hidden;
            transition: border-color 0.2s;
        }
        .company-card:hover { border-color: #484f58; }
        .company-summary {
            padding: 14px 18px;
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
        }
        .company-avatar {
            width: 32px;
            height: 32px;
            border-radius: 6px;
            background: #238636;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 15px;
        }
        .company-title {
            font-size: 16px;
            font-weight: 700;
            color: #f0f6fc;
            margin: 0;
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
            padding: 10px 18px;
            background: #161b22;
            color: var(--text-muted);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid var(--border-muted);
        }
        .opportunities-table td {
            padding: 10px 18px;
            border-bottom: 1px solid var(--border-muted);
            vertical-align: middle;
        }
        .opportunities-table tr:last-child td { border-bottom: none; }
        .opportunities-table tr:hover td { background: #1f242c; }

        .role-title {
            color: #f0f6fc;
            font-weight: 600;
            text-decoration: none;
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

        <!-- Stats Overview -->
        <div class="stats-bar">
            <div class="stat-card">
                <span class="stat-value">{total_companies}</span>
                <span class="stat-label">Verified Organizations</span>
            </div>
            <div class="stat-card">
                <span class="stat-value">{total_opportunities}</span>
                <span class="stat-label">Total Vacancies / Roles</span>
            </div>
            <div class="stat-card">
                <span class="stat-value">{verified_count}</span>
                <span class="stat-label">Verified Opportunities</span>
            </div>
        </div>

        <!-- Controls Toolbar -->
        <div class="toolbar">
            <form method="GET" class="search-box">
                <input type="text" id="searchInput" name="q" value="{query}" placeholder="Search opportunities by title, company, or skills...">
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
        function toggleAllCards() {
            const cards = document.querySelectorAll('details.company-card');
            if (!cards.length) return;
            const anyOpen = Array.from(cards).some(c => c.open);
            cards.forEach(c => c.open = !anyOpen);
        }

        // Fast Client-Side Real-Time Filter
        const input = document.getElementById('searchInput');
        input.addEventListener('input', function(e) {
            const filter = e.target.value.toLowerCase().trim();
            const cards = document.querySelectorAll('.company-card');
            cards.forEach(card => {
                const companyName = card.getAttribute('data-company').toLowerCase();
                const rows = card.querySelectorAll('.opp-row');
                let hasMatch = false;
                rows.forEach(row => {
                    const text = row.innerText.toLowerCase();
                    if (!filter || text.includes(filter) || companyName.includes(filter)) {
                        row.style.display = '';
                        hasMatch = true;
                    } else {
                        row.style.display = 'none';
                    }
                });
                card.style.display = hasMatch ? '' : 'none';
                if (filter && hasMatch) card.open = true;
            });
        });
    </script>
</body>
</html>
"""


class LocalViewerHandler(BaseHTTPRequestHandler):
    config: Config
    repo: Repository

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        search_query = params.get("q", [None])[0]

        opps = self.repo.list_opportunities(search_query=search_query, limit=500)

        # Group opportunities by company_name
        grouped: dict[str, list[Opportunity]] = {}
        for o in opps:
            grouped.setdefault(o.company_name, []).append(o)

        cards_html: list[str] = []
        verified_count = sum(1 for o in opps if o.admission_class == "VERIFIED")

        for company_name, company_opps in sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True):
            initial = company_name[:1].upper() if company_name else "O"
            total_jobs = len(company_opps)

            onsite_cnt = sum(1 for o in company_opps if o.work_mode.value == "onsite")
            remote_cnt = sum(1 for o in company_opps if o.work_mode.value == "remote")
            hybrid_cnt = sum(1 for o in company_opps if o.work_mode.value == "hybrid")

            mode_badges = []
            if remote_cnt:
                mode_badges.append(f"<span class='badge badge-remote'>{remote_cnt} Remote</span>")
            if hybrid_cnt:
                mode_badges.append(f"<span class='badge badge-hybrid'>{hybrid_cnt} Hybrid</span>")
            if onsite_cnt:
                mode_badges.append(f"<span class='badge badge-onsite'>{onsite_cnt} Onsite</span>")

            rows_html: list[str] = []
            for o in company_opps:
                badge_cls = "badge-verified" if o.admission_class == "VERIFIED" else "badge-lead"
                mode_cls = f"badge-{o.work_mode.value}" if o.work_mode.value in ("remote", "hybrid", "onsite") else "badge-onsite"

                role_type = "Job"
                ltitle = o.title.lower()
                if "intern" in ltitle:
                    role_type = "Internship"
                elif "trainee" in ltitle or "apprentice" in ltitle:
                    role_type = "Trainee"
                elif "fellow" in ltitle:
                    role_type = "Fellowship"

                rows_html.append(
                    f"<tr class='opp-row'>"
                    f"<td><a class='role-title' href='{html.escape(o.application_url)}' target='_blank' rel='noopener noreferrer'>{html.escape(o.title)}</a></td>"
                    f"<td><span class='badge badge-onsite'>{html.escape(role_type)}</span></td>"
                    f"<td>{html.escape(o.location_raw or 'Not disclosed')}</td>"
                    f"<td><span class='badge {mode_cls}'>{html.escape(o.work_mode.value)}</span></td>"
                    f"<td><span class='badge {badge_cls}'>{html.escape(o.admission_class)}</span></td>"
                    f"<td style='text-align:right;'><a class='btn-apply' href='{html.escape(o.application_url)}' target='_blank' rel='noopener noreferrer'>Apply ↗</a></td>"
                    f"</tr>"
                )

            cards_html.append(
                f"<details open class='company-card' data-company='{html.escape(company_name)}'>\n"
                f"  <summary class='company-summary'>\n"
                f"    <div class='company-header-left'>\n"
                f"      <div class='company-avatar'>{initial}</div>\n"
                f"      <div>\n"
                f"        <h2 class='company-title'>{html.escape(company_name)}</h2>\n"
                f"      </div>\n"
                f"      <span class='badge-count'>{total_jobs} {'open position' if total_jobs == 1 else 'open positions'}</span>\n"
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
                f"          <th style='width: 100px;'>Type</th>\n"
                f"          <th>Location</th>\n"
                f"          <th style='width: 90px;'>Work Mode</th>\n"
                f"          <th style='width: 110px;'>Admission</th>\n"
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
            .replace("{total_opportunities}", str(len(opps)))
            .replace("{verified_count}", str(verified_count))
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
