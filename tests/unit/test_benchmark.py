"""Unit tests for benchmark runner and scorecard computation."""

from openpath.config import Config
from openpath.evaluation.benchmark import BenchmarkRunner, BenchmarkScorecard


def test_load_reference_dataset(tmp_path) -> None:
    db_file = tmp_path / "test.db"
    config = Config(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        db_path=db_file,
    )
    runner = BenchmarkRunner(config)
    dataset = runner.load_reference_dataset()

    assert "organizations" in dataset
    assert len(dataset["organizations"]) == 100
    assert dataset["version"] == "1.0"


def test_benchmark_evaluate(tmp_path) -> None:
    from openpath.db.connection import DatabaseManager
    from openpath.db.migrations import apply_migrations

    db_file = tmp_path / "test.db"
    config = Config(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        db_path=db_file,
    )
    # Apply migrations to seed sources
    db_mgr = DatabaseManager(db_file)
    with db_mgr.transaction() as conn:
        apply_migrations(conn)

    runner = BenchmarkRunner(config)
    scorecard = runner.evaluate()

    assert isinstance(scorecard, BenchmarkScorecard)
    assert scorecard.total_reference_orgs == 100
    assert scorecard.covered_reference_orgs >= 1
    assert scorecard.verified_precision_pct >= 98.0
    assert scorecard.evidence_completeness_pct == 100.0
    assert scorecard.eligibility_accuracy_pct == 100.0
