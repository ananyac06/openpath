"""Textual Terminal User Interface for OpenPath."""

from __future__ import annotations

import json
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    Markdown,
    Static,
    TabbedContent,
    TabPane,
)

from openpath import __version__
from openpath.config import get_config
from openpath.db.connection import DatabaseManager
from openpath.db.repository import Repository
from openpath.diagnostics import run_diagnostics
from openpath.models.entities import Opportunity
from openpath.taxonomy import CAREER_STAGE_LABELS, FUNCTION_AREA_LABELS, classify_role


class OpenPathApp(App[None]):
    """OpenPath Interactive Research Console."""

    TITLE = "OpenPath Research Console"
    SUB_TITLE = f"v{__version__} | Local-first • India-first"
    CSS = """
    Screen {
        background: #0f141c;
        color: #e6edf3;
    }
    Header {
        background: #161b22;
        color: #58a6ff;
    }
    Footer {
        background: #161b22;
    }
    .panel {
        background: #161b22;
        border: solid #30363d;
        padding: 1;
        margin: 1;
    }
    .metric-box {
        background: #21262d;
        border: solid #30363d;
        padding: 1;
        margin: 1;
        height: 6;
        content-align: center middle;
    }
    .metric-value {
        text-style: bold;
        color: #3fb950;
    }
    DataTable {
        height: 1fr;
        border: solid #30363d;
    }
    #detail_pane {
        width: 45%;
        border-left: solid #30363d;
        padding: 1;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit", show=True),
        Binding("d", "switch_tab('tab_dashboard')", "Dashboard", show=True),
        Binding("r", "switch_tab('tab_results')", "Results", show=True),
        Binding("s", "switch_tab('tab_sources')", "Sources", show=True),
        Binding("m", "switch_tab('tab_monitor')", "Live Monitor", show=True),
        Binding("p", "switch_tab('tab_profiles')", "Profiles", show=True),
        Binding("e", "switch_tab('tab_evidence')", "Evidence", show=True),
        Binding("x", "switch_tab('tab_diagnostics')", "Diagnostics", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._result_opps: list[Opportunity] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs"):
            with TabPane("Dashboard (d)", id="tab_dashboard"):
                yield from self._compose_dashboard()
            with TabPane("Results Explorer (r)", id="tab_results"):
                yield from self._compose_results()
            with TabPane("Source Inventory (s)", id="tab_sources"):
                yield from self._compose_sources()
            with TabPane("Live Monitor (m)", id="tab_monitor"):
                yield from self._compose_monitor()
            with TabPane("Profiles (p)", id="tab_profiles"):
                yield from self._compose_profiles()
            with TabPane("Evidence & Verification (e)", id="tab_evidence"):
                yield from self._compose_evidence()
            with TabPane("System Diagnostics (x)", id="tab_diagnostics"):
                yield from self._compose_diagnostics()
            with TabPane("Export & History", id="tab_export"):
                yield from self._compose_export()
        yield Footer()

    # -------------------------------------------------------------------------
    # Screen Composers
    # -------------------------------------------------------------------------

    def _compose_dashboard(self) -> ComposeResult:
        with VerticalScroll():
            with Horizontal():
                with Container(classes="metric-box"):
                    yield Label("Verified Active Roles", classes="metric-title")
                    yield Label("0", id="dash_verified_count", classes="metric-value")
                with Container(classes="metric-box"):
                    yield Label("Needs Investigation", classes="metric-title")
                    yield Label("0", id="dash_investigate_count", classes="metric-value")
                with Container(classes="metric-box"):
                    yield Label("Declared Sources", classes="metric-title")
                    yield Label("0", id="dash_sources_count", classes="metric-value")
                with Container(classes="metric-box"):
                    yield Label("System Status", classes="metric-title")
                    yield Label("HEALTHY", id="dash_system_status", classes="metric-value")

            with Container(classes="panel"):
                yield Label("[bold cyan]Recent Research Activity[/bold cyan]")
                yield Static(
                    "Welcome to OpenPath Research Console.\n"
                    "• Press [bold]r[/bold] to browse opportunities with stage/function classification.\n"
                    "• Run [bold]openpath web[/bold] for curated collections (Start Here, Internships, Remote, India, etc.).\n"
                    "• Press [bold]s[/bold] to inspect source connectors.\n"
                    "• Press [bold]m[/bold] to view the live crawl monitor.\n"
                    "• Press [bold]x[/bold] to run system diagnostics.",
                    id="dash_recent_activity",
                )

    def _compose_results(self) -> ComposeResult:
        with Horizontal():
            with Vertical():
                with Horizontal():
                    yield Label("[bold cyan]Discovered Opportunities[/bold cyan]")
                    yield Button("Refresh", id="btn_refresh_results")
                yield Static(
                    "Classified by career stage and function from listing titles (unknowns are shown as unspecified, not guessed). "
                    "For curated, filterable collections, use: [bold]openpath web[/bold]",
                )
                yield DataTable(id="results_table")
            with VerticalScroll(id="detail_pane"):
                yield Label("[bold cyan]Opportunity Details & Evidence[/bold cyan]")
                yield Markdown(
                    "*Select an opportunity from the table to inspect details and evidence.*",
                    id="result_detail_markdown",
                )

    def _compose_sources(self) -> ComposeResult:
        with Vertical():
            with Horizontal():
                yield Label("[bold cyan]Declared Source Inventory & Health[/bold cyan]")
                yield Button("Refresh Sources", id="btn_refresh_sources")
            yield DataTable(id="sources_table")

    def _compose_monitor(self) -> ComposeResult:
        with VerticalScroll():
            with Container(classes="panel"):
                yield Label("[bold cyan]Live Research & Crawler Monitor[/bold cyan]")
                yield Static(
                    "Crawler status: [bold green]IDLE[/bold green]", id="monitor_status_text"
                )
            with Horizontal():
                with Container(classes="metric-box"):
                    yield Label("Requests Attempted", classes="metric-title")
                    yield Label("0", id="mon_req_attempted", classes="metric-value")
                with Container(classes="metric-box"):
                    yield Label("Requests Succeeded", classes="metric-title")
                    yield Label("0", id="mon_req_succeeded", classes="metric-value")
                with Container(classes="metric-box"):
                    yield Label("Pages Parsed", classes="metric-title")
                    yield Label("0", id="mon_pages_parsed", classes="metric-value")
                with Container(classes="metric-box"):
                    yield Label("Opportunities Extracted", classes="metric-title")
                    yield Label("0", id="mon_opps_extracted", classes="metric-value")
            with Container(classes="panel"):
                yield Label("[bold cyan]Crawl Task Frontier Queue[/bold cyan]")
                yield Static("No active crawler tasks in progress.", id="mon_queue_status")

    def _compose_profiles(self) -> ComposeResult:
        with Vertical():
            with Horizontal():
                yield Label("[bold cyan]Registered Candidate Profiles[/bold cyan]")
                yield Button("Refresh Profiles", id="btn_refresh_profiles")
            yield DataTable(id="profiles_table")

    def _compose_evidence(self) -> ComposeResult:
        with VerticalScroll():
            with Container(classes="panel"):
                yield Label("[bold cyan]Evidence & Audit Trail Inspector[/bold cyan]")
                yield Static(
                    "All facts in OpenPath are backed by cryptographic content hashes and verbatim source excerpts.\n"
                    "Select an opportunity in the Results tab to inspect its full evidence chain.",
                    id="evidence_summary_text",
                )
            yield DataTable(id="evidence_table")

    def _compose_diagnostics(self) -> ComposeResult:
        with VerticalScroll():
            with Horizontal():
                yield Label("[bold cyan]System Diagnostics & Environment[/bold cyan]")
                yield Button("Re-run Diagnostics", id="btn_run_diagnostics", variant="primary")
            yield DataTable(id="diagnostics_table")

    def _compose_export(self) -> ComposeResult:
        with VerticalScroll(), Container(classes="panel"):
            yield Label("[bold cyan]Export Research Records[/bold cyan]")
            yield Static(
                "Export verified opportunities with full evidence trails to JSON or Markdown formats."
            )
            with Horizontal():
                yield Button("Export to JSON", id="btn_export_json", variant="primary")
                yield Button("Export to Markdown", id="btn_export_md")
            yield Static("", id="export_status_label")

    # -------------------------------------------------------------------------
    # Lifecycle & Event Handlers
    # -------------------------------------------------------------------------

    def on_mount(self) -> None:
        """Initialize tables and load data from local repository upon launch."""
        self._init_results_table()
        self._init_sources_table()
        self._init_profiles_table()
        self._init_diagnostics_table()
        self._init_evidence_table()
        self.refresh_all_data()

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch active tab programmatically."""
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = tab_id

    def _init_results_table(self) -> None:
        table = self.query_one("#results_table", DataTable)
        table.cursor_type = "row"
        table.add_columns("ID", "Company", "Title", "Stage", "Function", "Location", "Mode", "Status")

    def _init_sources_table(self) -> None:
        table = self.query_one("#sources_table", DataTable)
        table.cursor_type = "row"
        table.add_columns("ID", "Name", "Category", "Authority Tier", "Access Method", "Status")

    def _init_profiles_table(self) -> None:
        table = self.query_one("#profiles_table", DataTable)
        table.cursor_type = "row"
        table.add_columns("ID", "Name", "Degree", "Year", "Discipline", "Skills")

    def _init_diagnostics_table(self) -> None:
        table = self.query_one("#diagnostics_table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Category", "Component", "Status", "Message")

    def _init_evidence_table(self) -> None:
        table = self.query_one("#evidence_table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Claim", "URL", "Excerpt")

    def refresh_all_data(self) -> None:
        """Reload all data from local database."""
        config = get_config()
        repo = Repository(DatabaseManager(config.db_path))

        # 1. Update stats
        stats = repo.get_stats()
        self.query_one("#dash_sources_count", Label).update(str(stats.get("sources", 0)))
        self.query_one("#dash_verified_count", Label).update(str(stats.get("opportunities", 0)))

        # 2. Populate Sources Table
        sources = repo.list_sources()
        src_table = self.query_one("#sources_table", DataTable)
        src_table.clear()
        for s in sources:
            src_table.add_row(
                s.id,
                s.name,
                s.category,
                s.authority_tier.value,
                s.access_method,
                s.last_status or "Ready",
            )

        # 3. Populate Results Table
        opps = repo.list_opportunities(limit=100)
        self._result_opps = opps
        res_table = self.query_one("#results_table", DataTable)
        res_table.clear()
        for o in opps:
            cls = classify_role(o.title)
            res_table.add_row(
                o.id[:8],
                o.company_name,
                o.title,
                CAREER_STAGE_LABELS[cls.stage],
                FUNCTION_AREA_LABELS[cls.function],
                o.location_raw or "Not disclosed",
                o.work_mode.value,
                o.admission_class,
            )

        # 4. Populate Profiles Table
        profiles = repo.list_profiles()
        prof_table = self.query_one("#profiles_table", DataTable)
        prof_table.clear()
        for p in profiles:
            year = "N/A" if p.academic_year is None else str(p.academic_year)
            prof_table.add_row(
                p.id[:8],
                p.name,
                p.degree or "N/A",
                year,
                p.discipline or "N/A",
                ", ".join(p.skills[:3]),
            )

        # 5. Populate Diagnostics
        self.run_diagnostics_refresh()

    def run_diagnostics_refresh(self) -> None:
        config = get_config()
        report = run_diagnostics(config)
        self.query_one("#dash_system_status", Label).update(report.overall_status)

        diag_table = self.query_one("#diagnostics_table", DataTable)
        diag_table.clear()
        for item in report.items:
            diag_table.add_row(item.category, item.name, item.status, item.message)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if (
            event.button.id == "btn_refresh_results"
            or event.button.id == "btn_refresh_sources"
            or event.button.id == "btn_refresh_profiles"
        ):
            self.refresh_all_data()
        elif event.button.id == "btn_run_diagnostics":
            self.run_diagnostics_refresh()
        elif event.button.id == "btn_export_json":
            self._handle_export_json()

    def _handle_export_json(self) -> None:
        config = get_config()
        repo = Repository(DatabaseManager(config.db_path))
        opps = repo.list_opportunities(limit=500)
        out_file = config.data_dir / "verified_opportunities.json"
        out_file.write_text(json.dumps([o.model_dump(mode="json") for o in opps], indent=2))
        self.query_one("#export_status_label", Static).update(
            f"[bold green]Successfully exported {len(opps)} opportunities to {out_file}[/bold green]"
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """When an opportunity row is clicked or selected, show details in the pane."""
        if event.data_table.id == "results_table":
            row_key = event.row_key
            row = event.data_table.get_row(row_key)
            opp_short_id = str(row[0])
            config = get_config()
            repo = Repository(DatabaseManager(config.db_path))
            candidates = self._result_opps or repo.list_opportunities(limit=500)
            target = next((o for o in candidates if o.id.startswith(opp_short_id)), None)
            if target:
                full_opp = repo.get_opportunity(target.id)
                if full_opp:
                    cls = classify_role(full_opp.title)
                    md_text = f"### {full_opp.title}\n\n"
                    md_text += f"**Company:** {full_opp.company_name}\n\n"
                    md_text += (
                        f"**Classification:** {CAREER_STAGE_LABELS[cls.stage]} · "
                        f"{FUNCTION_AREA_LABELS[cls.function]}\n\n"
                    )
                    md_text += (
                        f"**Location:** {full_opp.location_raw or 'Not disclosed'} "
                        f"({full_opp.work_mode.value})\n\n"
                    )
                    md_text += f"**Compensation:** {full_opp.compensation_raw}\n\n"
                    md_text += f"**Apply URL:** [{full_opp.application_url}]({full_opp.application_url})\n\n"
                    md_text += f"**Admission:** `{full_opp.admission_class}` | **Status:** `{full_opp.status}`\n\n"
                    md_text += "#### Verification Checks\n"
                    for chk in full_opp.checks:
                        md_text += (
                            f"- **{chk.check_name}:** `{chk.result.value}` — {chk.explanation}\n"
                        )
                    self.query_one("#result_detail_markdown", Markdown).update(md_text)


if __name__ == "__main__":
    app = OpenPathApp()
    app.run()
