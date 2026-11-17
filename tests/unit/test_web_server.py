"""Unit tests for local-only read-only web server."""

import threading
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
    with pytest.raises(ValueError, match=r"Security violation: OpenPath local web viewer can ONLY bind to 127\.0\.0\.1"):
        run_server(config, host="0.0.0.0", port=8765)

    with pytest.raises(ValueError, match="Security violation"):
        run_server(config, host="192.168.1.5", port=8765)


def test_server_get_request(tmp_path) -> None:
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
    repo = Repository(db_mgr)

    handler_cls = type(
        "ConfiguredTestHandler",
        (LocalViewerHandler,),
        {"config": config, "repo": repo},
    )

    # Bind to port 0 for an ephemeral available port
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        url = f"http://127.0.0.1:{port}/?q=engineer"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            assert resp.status == 200
            content = resp.read().decode("utf-8")
            assert "OpenPath Local Research Viewer" in content
            assert "127.0.0.1 Local Only" in content
    finally:
        server.shutdown()
        server.server_close()
