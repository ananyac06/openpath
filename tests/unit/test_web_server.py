"""Unit tests for local-only read-only web server."""

import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import HTTPServer

import pytest

from openpath.config import Config
from openpath.db.connection import DatabaseManager
from openpath.db.migrations import apply_migrations
from openpath.db.repository import Repository
from openpath.web.server import LocalViewerHandler, run_server


def test_server_bind_security_check(tmp_path) -> None:
    config = Config(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        db_path=tmp_path / "test.db",
    )
    with pytest.raises(
        ValueError,
        match=r"Security violation: OpenPath local web viewer can ONLY bind to 127\.0\.0\.1",
    ):
        run_server(config, host="0.0.0.0", port=8765)

    with pytest.raises(ValueError, match="Security violation"):
        run_server(config, host="192.168.1.5", port=8765)


def _start_server(tmp_path) -> tuple[HTTPServer, str]:
    db_file = tmp_path / "test.db"
    config = Config(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        db_path=db_file,
    )
    db_mgr = DatabaseManager(db_file)
    with db_mgr.transaction() as conn:
        apply_migrations(conn)

    from openpath.models.entities import (
        EvidenceRecord,
        Opportunity,
        VerificationCheck,
        VerificationResult,
        WorkMode,
    )

    repo = Repository(db_mgr)
    repo.save_opportunity(
        Opportunity(
            id="opp-web-1",
            company_name="Acme Cloud",
            title="Software Engineering Intern",
            locations=["Bengaluru, India"],
            work_mode=WorkMode.ONSITE,
            description_text="Python and Go backend internship for 2026 grads.",
            compensation_text="Rs 60,000 / month",
            canonical_application_url="https://boards.example.com/acme/1",
            admission_class="VERIFIED",
            status="active",
            source_ids=[],
            evidence=[
                EvidenceRecord(
                    id="ev-web-1",
                    opportunity_id="opp-web-1",
                    evidence_type="api_json_field",
                    claim="job_posting",
                    original_url="https://boards-api.example.com/v1/boards/acme/jobs/1",
                    excerpt="Python and Go backend internship",
                    content_hash="hash-1",
                    extraction_method="greenhouse_v1_api",
                )
            ],
            checks=[
                VerificationCheck(
                    id="chk-web-1",
                    opportunity_id="opp-web-1",
                    check_name="listing_existence",
                    result=VerificationResult.PASS,
                    explanation="Confirmed via live ATS endpoint",
                )
            ],
        )
    )
    repo.save_opportunity(
        Opportunity(
            id="opp-web-2",
            company_name="Acme Cloud",
            title="Principal Platform Engineer",
            locations=["Remote, United States"],
            work_mode=WorkMode.REMOTE,
            description_text="Distributed systems and kernel work.",
            compensation_text="Not disclosed",
            canonical_application_url="https://boards.example.com/acme/2",
            admission_class="VERIFIED",
            status="active",
            source_ids=[],
        )
    )

    handler_cls = type(
        "ConfiguredTestHandler",
        (LocalViewerHandler,),
        {"config": config, "repo": repo},
    )
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return server, f"http://127.0.0.1:{port}/"


def test_server_get_request(tmp_path) -> None:
    server, base = _start_server(tmp_path)
    try:
        url = f"{base}?q=engineer"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            assert resp.status == 200
            content = resp.read().decode("utf-8")
            assert "OpenPath" in content
            assert "Research Viewer" in content
            assert "127.0.0.1 Local Only" in content
    finally:
        server.shutdown()
        server.server_close()


MALFORMED_QUERIES = [
    "%22",  # unterminated double quote -> fts5 syntax error before the fix
    "NEAR(",
    "OR AND OR",
    "*",
    "^engineer",
    "engineer NEAR/3",
]


@pytest.mark.parametrize("query", MALFORMED_QUERIES)
def test_server_survives_malformed_search_queries(tmp_path, query) -> None:
    """A bad search box value must never take the viewer down.

    Before the fix each of these raised sqlite3.OperationalError, the request was
    dropped with no response at all and the connection died, so the local viewer
    looked dead to the user.
    """
    server, base = _start_server(tmp_path)
    try:
        url = f"{base}?q={urllib.parse.quote(query)}"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            assert resp.status == 200
            content = resp.read().decode("utf-8")
            assert "OpenPath" in content
            assert "Research Viewer" in content
    finally:
        server.shutdown()
        server.server_close()
