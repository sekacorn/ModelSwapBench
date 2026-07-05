from __future__ import annotations

import pytest

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
