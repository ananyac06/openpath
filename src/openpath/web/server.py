"""Local-only read-only web server for inspecting research results and evidence in a browser."""

from __future__ import annotations

import html
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from openpath.config import Config
from openpath.db.connection import DatabaseManager
from openpath.db.repository import Repository

logger = logging.getLogger(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>OpenPath Local Research Viewer</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0d1117; color: #c9d1d9; margin: 0; padding: 24px; }
        .container { max-width: 1200px; margin: 0 auto; }
        header { border-bottom: 1px solid #30363d; padding-bottom: 16px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; }
        h1 { color: #58a6ff; margin: 0; font-size: 24px; }
        .tag { background: #238636; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
        .search-box { margin-bottom: 20px; display: flex; gap: 10px; }
        input[type="text"] { background: #161b22; border: 1px solid #30363d; color: #c9d1d9; padding: 8px 12px; border-radius: 6px; flex-grow: 1; font-size: 14px; }
        button { background: #238636; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; background: #161b22; border: 1px solid #30363d; border-radius: 6px; overflow: hidden; }
        th, td { text-align: left; padding: 12px 16px; border-bottom: 1px solid #21262d; }
        th { background: #21262d; color: #8b949e; font-size: 12px; text-transform: uppercase; }
        tr:hover { background: #1f242c; }
        a { color: #58a6ff; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .badge-verified { background: rgba(56, 139, 253, 0.15); color: #58a6ff; padding: 2px 6px; border-radius: 4px; font-size: 12px; border: 1px solid rgba(56, 139, 253, 0.4); }
        .badge-lead { background: rgba(210, 153, 34, 0.15); color: #d29922; padding: 2px 6px; border-radius: 4px; font-size: 12px; border: 1px solid rgba(210, 153, 34, 0.4); }
        .evidence-card { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 16px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>OpenPath Local Research Viewer</h1>
                <p style="margin: 4px 0 0; color: #8b949e; font-size: 13px;">Local-first • India-first • Evidence-driven Opportunity Research</p>
            </div>
            <div>
                <span class="tag">127.0.0.1 Local Only</span>
            </div>
        </header>

        <form method="GET" class="search-box">
            <input type="text" name="q" value="{query}" placeholder="Search opportunities by title, company, or skills...">
            <button type="submit">Search</button>
        </form>

        <table>
            <thead>
                <tr>
                    <th>Company</th>
                    <th>Opportunity Title</th>
                    <th>Location</th>
                    <th>Mode</th>
                    <th>Admission Class</th>
                    <th>Direct Link</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
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

        opps = self.repo.list_opportunities(search_query=search_query, limit=100)

        rows_html = []
        for o in opps:
            badge_cls = "badge-verified" if o.admission_class == "VERIFIED" else "badge-lead"
            rows_html.append(
                f"<tr>"
                f"<td><strong>{html.escape(o.company_name)}</strong></td>"
                f"<td>{html.escape(o.title)}</td>"
                f"<td>{html.escape(o.location_raw or 'Not disclosed')}</td>"
                f"<td>{html.escape(o.work_mode.value)}</td>"
                f"<td><span class='{badge_cls}'>{html.escape(o.admission_class)}</span></td>"
                f"<td><a href='{html.escape(o.application_url)}' target='_blank' rel='noopener noreferrer'>Apply ↗</a></td>"
                f"</tr>"
            )

        if not rows_html:
            rows_html.append("<tr><td colspan='6' style='text-align:center; color:#8b949e; padding:32px;'>No opportunities found matching your query.</td></tr>")

        body = (
            HTML_TEMPLATE.replace("{query}", html.escape(search_query or ""))
            .replace("{rows}", "\n".join(rows_html))
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
        raise ValueError(f"Security violation: OpenPath local web viewer can ONLY bind to 127.0.0.1 or localhost (attempted: {host}).")

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
