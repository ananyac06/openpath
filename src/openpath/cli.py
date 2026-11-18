"""Command-line interface for OpenPath using Typer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from openpath import __version__
from openpath.config import get_config
from openpath.db.connection import DatabaseManager
from openpath.db.migrations import apply_migrations, get_applied_migrations
from openpath.db.repository import Repository
from openpath.diagnostics import run_diagnostics
from openpath.models.entities import CandidateProfile

app = typer.Typer(
    name="openpath",
    help="OpenPath: Local-first, TUI-first, evidence-driven opportunity research engine.",
    add_completion=False,
    no_args_is_help=False,
)

sources_app = typer.Typer(help="Manage and inspect declared sources and connectors.")
profiles_app = typer.Typer(help="Manage and validate candidate profiles.")
research_app = typer.Typer(help="Plan, execute, and monitor research runs.")
results_app = typer.Typer(help="Explore and inspect discovered opportunities.")
database_app = typer.Typer(help="Database operations, integrity checks, and migrations.")
evidence_app = typer.Typer(help="Inspect evidence records and provenance.")
companies_app = typer.Typer(help="Inspect organisations and verified domains.")
report_app = typer.Typer(help="Export research reports and benchmarks.")

app.add_typer(sources_app, name="sources")
app.add_typer(profiles_app, name="profiles")
app.add_typer(research_app, name="research")
app.add_typer(results_app, name="results")
app.add_typer(database_app, name="database")
app.add_typer(evidence_app, name="evidence")
app.add_typer(companies_app, name="companies")
app.add_typer(report_app, name="report")

console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool, typer.Option("--version", "-v", help="Show OpenPath version.")
    ] = False,
) -> None:
    """OpenPath main entry point. Launches the interactive Textual TUI when called without subcommands."""
    if version:
        console.print(f"[bold green]OpenPath[/bold green] version [cyan]{__version__}[/cyan]")
        raise typer.Exit()

    # If no subcommand is invoked, launch the Textual TUI application
    if ctx.invoked_subcommand is None:
        try:
            from openpath.tui.app import OpenPathApp

            tui_app = OpenPathApp()
            tui_app.run()
        except KeyboardInterrupt:
            pass
        except Exception as err:
            console.print(f"[bold red]Failed to start TUI:[/bold red] {err}")
            raise typer.Exit(code=1) from err


@app.command("doctor")
def doctor_cmd() -> None:
    """Run full environment, filesystem, and database diagnostics."""
    config = get_config()
    report = run_diagnostics(config)

    table = Table(title="OpenPath System Diagnostics", show_lines=True)
    table.add_column("Category", style="cyan", width=14)
    table.add_column("Component", style="bold", width=22)
    table.add_column("Status", justify="center", width=8)
    table.add_column("Message", style="dim")

    for item in report.items:
        if item.status == "PASS":
            status_badge = "[bold green]PASS[/bold green]"
        elif item.status == "WARN":
            status_badge = "[bold yellow]WARN[/bold yellow]"
        else:
            status_badge = "[bold red]FAIL[/bold red]"

        table.add_row(item.category, item.name, status_badge, item.message)

    console.print(table)

    if report.overall_status == "HEALTHY":
        console.print(
            Panel(
                "[bold green]All systems healthy and operational.[/bold green]\n"
                f"Config: {config.config_file}\nDatabase: {config.db_path}",
                title="Status: HEALTHY",
                border_style="green",
            )
        )
    elif report.overall_status == "DEGRADED":
        console.print(
            Panel(
                "[bold yellow]System operational with warnings. Review items above.[/bold yellow]",
                title="Status: DEGRADED",
                border_style="yellow",
            )
        )
    else:
        console.print(
            Panel(
                "[bold red]Diagnostic failures detected. Please correct the issues above.[/bold red]",
                title="Status: UNHEALTHY",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)


@app.command("serve")
def serve_cmd(
    host: Annotated[
        str,
        typer.Option(
            "--host", "-h", help="Host interface to bind (strictly 127.0.0.1 or localhost)."
        ),
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Port to listen on.")] = 8765,
) -> None:
    """Launch the local-only read-only web inspector."""
    from openpath.web.server import run_server

    config = get_config()
    try:
        run_server(config, host=host, port=port)
    except ValueError as err:
        console.print(f"[bold red]Configuration error:[/bold red] {err}")
        raise typer.Exit(code=1) from err


# -----------------------------------------------------------------------------
# Database Commands
# -----------------------------------------------------------------------------


@database_app.command("check")
def database_check_cmd() -> None:
    """Verify SQLite database integrity and migration status."""
    config = get_config()
    db_mgr = DatabaseManager(config.db_path)

    ok, msg = db_mgr.check_integrity()
    if not ok:
        console.print(f"[bold red]Integrity check failed:[/bold red] {msg}")
        raise typer.Exit(code=1)

    fts_ok = db_mgr.check_fts5_support()
    with db_mgr.connection() as conn:
        applied = get_applied_migrations(conn)

    table = Table(title="Database Health", show_lines=True)
    table.add_column("Check", style="cyan")
    table.add_column("Value", style="bold")
    table.add_row("Database File", str(config.db_path))
    table.add_row("PRAGMA integrity_check", f"[green]{msg}[/green]" if ok else f"[red]{msg}[/red]")
    table.add_row(
        "FTS5 Full-Text Search", "[green]Active[/green]" if fts_ok else "[red]Missing[/red]"
    )
    table.add_row("Applied Migrations", ", ".join(str(v) for v in sorted(applied)) or "None")

    console.print(table)


@database_app.command("migrate")
def database_migrate_cmd() -> None:
    """Apply any pending database schema migrations."""
    config = get_config()
    db_mgr = DatabaseManager(config.db_path)
    with db_mgr.transaction() as conn:
        applied = apply_migrations(conn)

    if applied:
        console.print(f"[bold green]Successfully applied migrations:[/bold green] {applied}")
    else:
        console.print("[cyan]Database schema is already up to date.[/cyan]")


# -----------------------------------------------------------------------------
# Sources Commands
# -----------------------------------------------------------------------------


@sources_app.command("list")
def sources_list_cmd(
    enabled_only: Annotated[
        bool, typer.Option("--enabled-only", "-e", help="Show only enabled sources")
    ] = False,
) -> None:
    """List declared opportunity sources."""
    config = get_config()
    repo = Repository(DatabaseManager(config.db_path))
    sources = repo.list_sources(enabled_only=enabled_only)

    if not sources:
        console.print(
            "[yellow]No sources found. Run `openpath database migrate` to seed sources.[/yellow]"
        )
        return

    table = Table(title="OpenPath Declared Source Inventory", show_lines=True)
    table.add_column("Source ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Category", style="magenta")
    table.add_column("Authority Tier", style="green")
    table.add_column("Access Method")
    table.add_column("Status")

    for s in sources:
        status_str = "[green]Enabled[/green]" if s.enabled else "[dim]Disabled[/dim]"
        if s.last_status:
            status_str += f" ({s.last_status})"
        table.add_row(s.id, s.name, s.category, s.authority_tier.value, s.access_method, status_str)

    console.print(table)


@sources_app.command("inspect")
def sources_inspect_cmd(source_id: str) -> None:
    """Inspect detailed configuration and metadata for a specific source."""
    config = get_config()
    repo = Repository(DatabaseManager(config.db_path))
    source = repo.get_source(source_id)
    if not source:
        console.print(f"[bold red]Source '{source_id}' not found.[/bold red]")
        raise typer.Exit(code=1)

    table = Table(title=f"Source: {source.name} ({source.id})", show_header=False)
    table.add_column("Property", style="cyan", width=20)
    table.add_column("Value")

    table.add_row("Connector ID", source.connector_id)
    table.add_row("Category", source.category)
    table.add_row("Base URL", source.base_url or "None")
    table.add_row("Authority Tier", source.authority_tier.value)
    table.add_row("Access Method", source.access_method)
    table.add_row("Policy URL", source.policy_url or "None")
    table.add_row("Enabled", "Yes" if source.enabled else "No")
    table.add_row("Last Status", source.last_status or "Never run")
    table.add_row("Last Checked At", source.last_checked_at or "Never")
    table.add_row("Metadata", json.dumps(source.metadata, indent=2))

    console.print(table)


# -----------------------------------------------------------------------------
# Profiles Commands
# -----------------------------------------------------------------------------


@profiles_app.command("list")
def profiles_list_cmd() -> None:
    """List registered candidate profiles."""
    config = get_config()
    repo = Repository(DatabaseManager(config.db_path))
    profiles = repo.list_profiles()

    if not profiles:
        console.print(
            "[yellow]No candidate profiles registered. Add one using `openpath profiles add`.[/yellow]"
        )
        return

    table = Table(title="Candidate Profiles", show_lines=True)
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold cyan")
    table.add_column("Degree")
    table.add_column("Year")
    table.add_column("Skills")
    table.add_column("India Auth")

    for p in profiles:
        table.add_row(
            p.id[:8] + "...",
            p.name,
            p.degree or "N/A",
            str(p.academic_year) if p.academic_year else "N/A",
            ", ".join(p.skills[:4]) + ("..." if len(p.skills) > 4 else ""),
            "Yes" if p.india_work_authorized else "No",
        )

    console.print(table)


@profiles_app.command("add")
def profiles_add_cmd(
    name: Annotated[str, typer.Option("--name", "-n", help="Candidate profile name")],
    degree: Annotated[
        str | None, typer.Option("--degree", "-d", help="Degree (e.g. B.Tech)")
    ] = "B.Tech",
    year: Annotated[
        int | None, typer.Option("--year", "-y", help="Current academic year (1-4)")
    ] = 3,
    discipline: Annotated[
        str, typer.Option("--discipline", help="Technical discipline")
    ] = "Computer Science",
    skills: Annotated[
        str, typer.Option("--skills", "-s", help="Comma-separated technical skills")
    ] = "Python,SQL,FastAPI",
) -> None:
    """Create and persist a new candidate profile."""
    config = get_config()
    repo = Repository(DatabaseManager(config.db_path))

    skill_list = [s.strip() for s in skills.split(",") if s.strip()]
    profile = CandidateProfile(
        name=name,
        degree=degree,
        academic_year=year,
        discipline=discipline,
        skills=skill_list,
    )
    repo.upsert_profile(profile)
    console.print(
        f"[bold green]Profile '{name}' successfully created with ID:[/bold green] {profile.id}"
    )


@profiles_app.command("validate")
def profiles_validate_cmd(profile_path: Path) -> None:
    """Validate a candidate profile JSON file against the schema."""
    if not profile_path.is_file():
        console.print(f"[bold red]File not found:[/bold red] {profile_path}")
        raise typer.Exit(code=1)

    try:
        content = profile_path.read_text(encoding="utf-8")
        data = json.loads(content)
        profile = CandidateProfile.model_validate(data)
        console.print(f"[bold green]Valid candidate profile:[/bold green] {profile.name}")
    except Exception as err:
        console.print(f"[bold red]Validation failed:[/bold red] {err}")
        raise typer.Exit(code=1) from err


# -----------------------------------------------------------------------------
# Results & Research Commands
# -----------------------------------------------------------------------------


@results_app.command("list")
def results_list_cmd(
    status: Annotated[
        str | None,
        typer.Option(
            "--status",
            "-s",
            help="Filter by status (verified, needs_investigation, community_lead)",
        ),
    ] = None,
    query: Annotated[
        str | None, typer.Option("--query", "-q", help="Full text search query")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-l", help="Max results to display")] = 20,
) -> None:
    """List discovered opportunities from the local research database."""
    config = get_config()
    repo = Repository(DatabaseManager(config.db_path))

    results = repo.list_opportunities(status=status, search_query=query, limit=limit)

    if not results:
        console.print("[yellow]No opportunities found matching your criteria.[/yellow]")
        return

    table = Table(title=f"Opportunities ({len(results)} shown)", show_lines=True)
    table.add_column("ID", style="dim", no_wrap=False)
    table.add_column("Company", style="bold cyan")
    table.add_column("Title", style="bold")
    table.add_column("Location")
    table.add_column("Mode", width=8)
    table.add_column("Admission Class", width=18)

    for o in results:
        status_color = (
            "green"
            if o.admission_class == "VERIFIED"
            else ("yellow" if o.admission_class == "NEEDS INVESTIGATION" else "dim")
        )
        table.add_row(
            o.id,
            o.company_name,
            o.title,
            o.location_raw or "Not disclosed",
            o.work_mode.value,
            f"[{status_color}]{o.admission_class}[/{status_color}]",
        )

    console.print(table)


@results_app.command("inspect")
def results_inspect_cmd(opportunity_id: str) -> None:
    """Inspect complete opportunity details, evidence claims, and verification checks."""
    config = get_config()
    repo = Repository(DatabaseManager(config.db_path))
    opp = repo.get_opportunity(opportunity_id)
    if not opp:
        console.print(f"[bold red]Opportunity '{opportunity_id}' not found.[/bold red]")
        raise typer.Exit(code=1)

    console.print(
        Panel(
            f"[bold]{opp.title}[/bold] at [cyan]{opp.company_name}[/cyan]\nApply URL: {opp.application_url}",
            title=f"Opportunity {opp.id}",
        )
    )

    # Verification Checks Table
    chk_table = Table(title="Independent Verification Checks", show_lines=True)
    chk_table.add_column("Check Name", style="cyan")
    chk_table.add_column("Outcome", justify="center")
    chk_table.add_column("Explanation")

    for chk in opp.checks:
        outcome = (
            "[bold green]PASS[/bold green]"
            if chk.result.value == "PASS"
            else (
                "[bold red]FAIL[/bold red]"
                if chk.result.value == "FAIL"
                else "[bold yellow]UNKNOWN[/bold yellow]"
            )
        )
        chk_table.add_row(chk.check_name, outcome, chk.explanation)
    console.print(chk_table)

    # Evidence Table
    if opp.evidence:
        ev_table = Table(title="Supporting Evidence Trail", show_lines=True)
        ev_table.add_column("Claim", style="cyan", width=15)
        ev_table.add_column("Source URL", style="dim")
        ev_table.add_column("Verbatim Excerpt")
        for ev in opp.evidence:
            ev_table.add_row(
                ev.claim,
                ev.original_url,
                (ev.excerpt or "")[:120] + ("..." if ev.excerpt and len(ev.excerpt) > 120 else ""),
            )
        console.print(ev_table)


@research_app.command("plan")
def research_plan_cmd(
    profile_id: Annotated[
        str | None, typer.Option("--profile", "-p", help="Target candidate profile ID")
    ] = None,
) -> None:
    """Generate a targeted research plan based on candidate profile and declared sources."""
    config = get_config()
    repo = Repository(DatabaseManager(config.db_path))
    sources = repo.list_sources(enabled_only=True)

    console.print(
        Panel(
            f"Planned research targets: [bold cyan]{len(sources)} enabled sources[/bold cyan] across ATS and official registries.",
            title="Research Plan",
        )
    )
    for s in sources:
        console.print(
            f" • [{s.authority_tier.value}] [bold]{s.name}[/bold] ({s.connector_id}) -> {s.base_url}"
        )


@research_app.command("run")
def research_run_cmd(
    source: Annotated[
        str | None, typer.Option("--source", "-s", help="Run research for a specific source ID")
    ] = None,
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Profile to evaluate eligibility against")
    ] = None,
) -> None:
    """Execute live research crawl across declared sources."""
    from openpath.crawler.orchestrator import ResearchOrchestrator

    config = get_config()
    orchestrator = ResearchOrchestrator(config)
    console.print("[bold green]Starting research run...[/bold green]")
    import asyncio

    run_record = asyncio.run(orchestrator.execute_run(source_id=source, profile_id=profile))
    console.print(f"[bold green]Research run completed![/bold green] Status: {run_record.status}")


@evidence_app.command("inspect")
def evidence_inspect_cmd(evidence_id: str) -> None:
    """Inspect a specific evidence record."""
    config = get_config()
    db_mgr = DatabaseManager(config.db_path)
    with db_mgr.connection() as conn:
        row = conn.execute(
            "SELECT * FROM evidence_records WHERE id = ?;", (evidence_id,)
        ).fetchone()
        if not row:
            console.print(f"[bold red]Evidence record '{evidence_id}' not found.[/bold red]")
            raise typer.Exit(code=1)

        console.print(Panel(json.dumps(dict(row), indent=2), title=f"Evidence {evidence_id}"))


@companies_app.command("inspect")
def companies_inspect_cmd(company_id: str) -> None:
    """Inspect an organisation and its verified domain mappings."""
    config = get_config()
    db_mgr = DatabaseManager(config.db_path)
    with db_mgr.connection() as conn:
        row = conn.execute("SELECT * FROM organisations WHERE id = ?;", (company_id,)).fetchone()
        if not row:
            console.print(f"[bold red]Company '{company_id}' not found.[/bold red]")
            raise typer.Exit(code=1)

        console.print(Panel(json.dumps(dict(row), indent=2), title=f"Organisation {company_id}"))


@report_app.command("export")
def report_export_cmd(
    format: Annotated[
        str, typer.Option("--format", "-f", help="Export format: json or markdown")
    ] = "json",
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Output file destination")
    ] = None,
) -> None:
    """Export verified research results and audit reports."""
    config = get_config()
    repo = Repository(DatabaseManager(config.db_path))
    opportunities = repo.list_opportunities(status="VERIFIED", limit=1000)

    export_data = [o.model_dump(mode="json") for o in opportunities]
    json_str = json.dumps(export_data, indent=2)

    if output:
        output.write_text(json_str, encoding="utf-8")
        console.print(
            f"[bold green]Exported {len(opportunities)} verified opportunities to {output}[/bold green]"
        )
    else:
        console.print(json_str)


@report_app.command("benchmark")
def report_benchmark_cmd() -> None:
    """Run quantitative research benchmark evaluation against reference dataset."""
    from openpath.evaluation.benchmark import BenchmarkRunner

    config = get_config()
    runner = BenchmarkRunner(config)
    scorecard = runner.evaluate()

    table = Table(title="OpenPath Benchmark Scorecard", show_lines=True)
    table.add_column("Evaluation Metric", style="cyan")
    table.add_column("Observed Value", justify="center", style="bold")
    table.add_column("Target Standard", style="dim")

    table.add_row(
        "Verified Precision", f"[green]{scorecard.verified_precision_pct:.1f}%[/green]", ">= 98.0%"
    )
    table.add_row(
        "Evidence Completeness",
        f"[green]{scorecard.evidence_completeness_pct:.1f}%[/green]",
        "100.0%",
    )
    table.add_row(
        "Eligibility Accuracy",
        f"[green]{scorecard.eligibility_accuracy_pct:.1f}%[/green]",
        "100.0% (Zero hallucinated inferences)",
    )
    table.add_row(
        "India Accessibility Accuracy",
        f"[green]{scorecard.india_accessibility_accuracy_pct:.1f}%[/green]",
        ">= 98.0%",
    )
    table.add_row(
        "Duplicate Survival Rate",
        f"[green]{scorecard.duplicate_survival_rate_pct:.1f}%[/green]",
        "< 2.0%",
    )
    table.add_row(
        "Reference Inventory Coverage",
        f"{scorecard.covered_reference_orgs} / {scorecard.total_reference_orgs} ({scorecard.source_coverage_pct:.1f}%)",
        "Stratified 100 orgs",
    )

    console.print(table)
    console.print(
        Panel(
            f"Overall Benchmark Status: [bold green]{scorecard.overall_score}[/bold green]",
            border_style="green",
        )
    )


def run_cli() -> None:
    """Console script entry point."""
    app()


if __name__ == "__main__":
    run_cli()
