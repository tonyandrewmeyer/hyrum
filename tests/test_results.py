from __future__ import annotations

import json
import pathlib

import pytest

from hyrum import pool
from hyrum import results as results_io


def _outcome(name: str, status: str, **kw) -> pool.Outcome:
    return pool.Outcome(repo=pathlib.Path(f'/charms/{name}'), status=status, **kw)


def test_save_creates_file_with_version(tmp_path: pathlib.Path):
    path = tmp_path / 'results.json'
    results_io.save([_outcome('alpha', 'passed')], path)
    data = json.loads(path.read_text())
    assert data['version'] == results_io.SCHEMA_VERSION


def test_round_trip_preserves_all_fields(tmp_path: pathlib.Path):
    original = [
        _outcome('alpha', 'passed', runner='tox', target='unit', duration_s=1.5, returncode=0),
        _outcome('beta', 'failed', runner='make', target='lint', duration_s=0.3, returncode=1),
        _outcome('gamma', 'skipped', skip_reason='no Makefile'),
        _outcome('delta', 'patcher_error', target='unit', error='lock failed'),
        pool.Outcome(repo=pathlib.Path('/charms/epsilon'), status='timeout', returncode=None),
    ]
    path = tmp_path / 'results.json'
    results_io.save(original, path)
    loaded = results_io.load(path)

    assert len(loaded) == len(original)
    for got, want in zip(loaded, original, strict=True):
        assert got == want


def test_round_trip_repo_path_survives_serialisation(tmp_path: pathlib.Path):
    path = tmp_path / 'results.json'
    repo = pathlib.Path('/home/user/.cache/hyrum/charms/my-charm')
    results_io.save([pool.Outcome(repo=repo, status='passed')], path)
    loaded = results_io.load(path)
    assert loaded[0].repo == repo


def test_load_raises_on_schema_version_mismatch(tmp_path: pathlib.Path):
    path = tmp_path / 'results.json'
    path.write_text(json.dumps({'version': 999, 'outcomes': []}))
    with pytest.raises(ValueError, match='schema version mismatch'):
        results_io.load(path)


def test_load_raises_on_missing_version(tmp_path: pathlib.Path):
    path = tmp_path / 'results.json'
    path.write_text(json.dumps({'outcomes': []}))
    with pytest.raises(ValueError, match='schema version mismatch'):
        results_io.load(path)


def test_save_empty_outcomes(tmp_path: pathlib.Path):
    path = tmp_path / 'results.json'
    results_io.save([], path)
    loaded = results_io.load(path)
    assert loaded == []
