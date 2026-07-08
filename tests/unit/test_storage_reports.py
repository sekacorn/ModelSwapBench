from __future__ import annotations

import pytest
import yaml

from model_swap_bench.config import build_suite
from model_swap_bench.errors import StorageError
from model_swap_bench.execution import BenchmarkRunner
from model_swap_bench.reports import render_csv, render_html, render_json, render_markdown
from model_swap_bench.storage import RunRepository


async def _run_and_save(suite, root):  # type: ignore[no-untyped-def]
    run = await BenchmarkRunner(suite).run()
    repo = RunRepository(root)
    repo.save(run, suite)
    return run, repo


async def test_repository_roundtrip(suite, tmp_repo_root) -> None:  # type: ignore[no-untyped-def]
    run, repo = await _run_and_save(suite, tmp_repo_root)
    loaded = repo.load("latest")
    assert loaded.run_id == run.run_id
    assert len(repo.list_runs()) == 1
    assert repo.latest() == run.run_id


async def test_repository_delete(suite, tmp_repo_root) -> None:  # type: ignore[no-untyped-def]
    run, repo = await _run_and_save(suite, tmp_repo_root)
    repo.delete(run.run_id)
    assert repo.list_runs() == []
    with pytest.raises(StorageError):
        repo.load(run.run_id)


async def test_manifest_and_suite_snapshot(suite, tmp_repo_root) -> None:  # type: ignore[no-untyped-def]
    run, repo = await _run_and_save(suite, tmp_repo_root)
    manifest = repo.load_manifest(run.run_id)
    assert manifest["suite_name"] == suite.name
    assert manifest["package_version"]
    snapshot = repo.load_suite_snapshot(run.run_id)
    assert snapshot.name == suite.name


async def test_suite_snapshot_copies_deterministic_fixtures(tmp_path) -> None:  # type: ignore[no-untyped-def]
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    fixture = suite_dir / "fixture.yaml"
    fixture.write_text(
        yaml.safe_dump({"cases": {"c1": {"output": {"category": "billing"}, "tokens": {"input": 10, "output": 2}}}}),
        encoding="utf-8",
    )
    suite = build_suite(
        {
            "name": "fixture-suite",
            "version": "1.0",
            "models": [
                {
                    "alias": "candidate",
                    "provider": "deterministic",
                    "model": "fixture",
                    "deployment": "test",
                    "fixture": "fixture.yaml",
                }
            ],
            "cases": [{"id": "c1", "input": {"message": "hi"}, "expected": {"category": "billing"}}],
            "evaluators": ["json_parse", "field_match"],
            "constraints": {"minimum_success_rate": 1.0},
        }
    )
    run = await BenchmarkRunner(suite, suite_dir=suite_dir).run()
    repo = RunRepository(tmp_path / "repo")
    repo.save(run, suite, suite_dir=suite_dir)

    snapshot = repo.load_suite_snapshot(run.run_id)
    assert snapshot.models[0].fixture == "fixtures/candidate-fixture.yaml"
    assert (repo.run_dir(run.run_id) / snapshot.models[0].fixture).exists()


async def test_reports_render(suite, tmp_repo_root) -> None:  # type: ignore[no-untyped-def]
    run, _repo = await _run_and_save(suite, tmp_repo_root)
    md = render_markdown(run, suite=suite)
    assert "Executive summary" in md and "Known limitations" in md
    assert "model_alias" in render_csv(run)
    assert '"run_id"' in render_json(run)
    assert "<html" in render_html(run)


async def test_latest_without_runs(tmp_repo_root) -> None:  # type: ignore[no-untyped-def]
    repo = RunRepository(tmp_repo_root)
    with pytest.raises(StorageError):
        repo.resolve("latest")
