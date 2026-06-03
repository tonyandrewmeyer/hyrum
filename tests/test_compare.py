from __future__ import annotations

import io
import pathlib

import rich.console
from click import testing

from hyrum import cli, pool
from hyrum import compare as compare_mod
from hyrum import results as results_io


def _outcome(name: str, status: str) -> pool.Outcome:
    return pool.Outcome(repo=pathlib.Path(f'/charms/{name}'), status=status)


def _render_to_str(result: compare_mod.CompareResult) -> str:
    buf = io.StringIO()
    console = rich.console.Console(file=buf, highlight=False, markup=False)
    compare_mod.render(result, console=console)
    return buf.getvalue()


# ── diff categories ────────────────────────────────────────────────────────────


def test_diff_new_failures():
    baseline = [_outcome('alpha', 'passed'), _outcome('beta', 'passed')]
    current = [_outcome('alpha', 'failed'), _outcome('beta', 'passed')]
    result = compare_mod.diff(baseline, current)
    assert result.new_failures == ['/charms/alpha']
    assert result.resolved == []
    assert result.new_errors == []


def test_diff_resolved():
    baseline = [_outcome('alpha', 'failed'), _outcome('beta', 'passed')]
    current = [_outcome('alpha', 'passed'), _outcome('beta', 'passed')]
    result = compare_mod.diff(baseline, current)
    assert result.resolved == ['/charms/alpha']
    assert result.new_failures == []
    assert result.new_errors == []


def test_diff_new_patcher_error():
    baseline = [_outcome('alpha', 'passed')]
    current = [_outcome('alpha', 'patcher_error')]
    result = compare_mod.diff(baseline, current)
    assert result.new_errors == ['/charms/alpha']
    assert result.new_failures == []
    assert result.resolved == []


def test_diff_new_timeout():
    baseline = [_outcome('alpha', 'passed')]
    current = [_outcome('alpha', 'timeout')]
    result = compare_mod.diff(baseline, current)
    assert result.new_errors == ['/charms/alpha']
    assert result.new_failures == []


def test_diff_existing_error_not_counted_as_new():
    baseline = [_outcome('alpha', 'patcher_error'), _outcome('beta', 'timeout')]
    current = [_outcome('alpha', 'patcher_error'), _outcome('beta', 'timeout')]
    result = compare_mod.diff(baseline, current)
    assert result.new_errors == []
    assert result.new_failures == []
    assert result.resolved == []


def test_diff_all_categories_simultaneously():
    baseline = [
        _outcome('a', 'passed'),  # → will fail: new_failure
        _outcome('b', 'failed'),  # → will pass: resolved
        _outcome('c', 'passed'),  # → patcher_error: new_error
        _outcome('d', 'passed'),  # unchanged
    ]
    current = [
        _outcome('a', 'failed'),
        _outcome('b', 'passed'),
        _outcome('c', 'patcher_error'),
        _outcome('d', 'passed'),
    ]
    result = compare_mod.diff(baseline, current)
    assert result.new_failures == ['/charms/a']
    assert result.resolved == ['/charms/b']
    assert result.new_errors == ['/charms/c']


# ── pass-rate delta ────────────────────────────────────────────────────────────


def test_pass_rate_delta_positive():
    baseline = [_outcome('a', 'failed'), _outcome('b', 'failed')]
    current = [_outcome('a', 'passed'), _outcome('b', 'passed')]
    result = compare_mod.diff(baseline, current)
    assert result.baseline_pass_rate == 0.0
    assert result.current_pass_rate == 1.0


def test_pass_rate_delta_negative():
    baseline = [_outcome('a', 'passed'), _outcome('b', 'passed')]
    current = [_outcome('a', 'failed'), _outcome('b', 'failed')]
    result = compare_mod.diff(baseline, current)
    assert result.baseline_pass_rate == 1.0
    assert result.current_pass_rate == 0.0


def test_pass_rate_excludes_skipped_and_no_target():
    baseline = [
        _outcome('a', 'passed'),
        _outcome('b', 'skipped'),
        _outcome('c', 'no_target'),
    ]
    current = [
        _outcome('a', 'passed'),
        _outcome('b', 'skipped'),
        _outcome('c', 'no_target'),
    ]
    result = compare_mod.diff(baseline, current)
    assert result.baseline_ran == 1
    assert result.current_ran == 1
    assert result.baseline_pass_rate == 1.0


def test_pass_rate_zero_ran_gives_zero_rate():
    baseline: list[pool.Outcome] = []
    current: list[pool.Outcome] = []
    result = compare_mod.diff(baseline, current)
    assert result.baseline_pass_rate == 0.0
    assert result.current_pass_rate == 0.0


# ── render output ──────────────────────────────────────────────────────────────


def test_render_no_changes_message():
    baseline = [_outcome('alpha', 'passed')]
    current = [_outcome('alpha', 'passed')]
    result = compare_mod.diff(baseline, current)
    output = _render_to_str(result)
    assert 'No changes between runs' in output


def test_render_shows_pass_rate_delta():
    baseline = [_outcome('a', 'passed'), _outcome('b', 'failed')]
    current = [_outcome('a', 'failed'), _outcome('b', 'passed')]
    result = compare_mod.diff(baseline, current)
    output = _render_to_str(result)
    assert 'Pass rate' in output
    assert 'delta' in output


# ── CLI compare subcommand ─────────────────────────────────────────────────────


def _write_results(path: pathlib.Path, outcomes: list[pool.Outcome]) -> None:
    results_io.save(outcomes, path)


def test_compare_subcommand_exits_zero_when_no_regression(tmp_path: pathlib.Path):
    baseline_path = tmp_path / 'baseline.json'
    current_path = tmp_path / 'current.json'
    _write_results(baseline_path, [_outcome('alpha', 'passed')])
    _write_results(current_path, [_outcome('alpha', 'passed')])

    result = testing.CliRunner().invoke(
        cli.main,
        ['compare', str(baseline_path), str(current_path)],
    )
    assert result.exit_code == 0, result.output


def test_compare_fail_on_regression_exits_nonzero_on_new_failure(tmp_path: pathlib.Path):
    baseline_path = tmp_path / 'baseline.json'
    current_path = tmp_path / 'current.json'
    _write_results(baseline_path, [_outcome('alpha', 'passed')])
    _write_results(current_path, [_outcome('alpha', 'failed')])

    result = testing.CliRunner().invoke(
        cli.main,
        ['compare', '--fail-on-regression', str(baseline_path), str(current_path)],
    )
    assert result.exit_code == 1, result.output


def test_compare_fail_on_regression_exits_nonzero_on_new_error(tmp_path: pathlib.Path):
    baseline_path = tmp_path / 'baseline.json'
    current_path = tmp_path / 'current.json'
    _write_results(baseline_path, [_outcome('alpha', 'passed')])
    _write_results(current_path, [_outcome('alpha', 'patcher_error')])

    result = testing.CliRunner().invoke(
        cli.main,
        ['compare', '--fail-on-regression', str(baseline_path), str(current_path)],
    )
    assert result.exit_code == 1, result.output


def test_compare_fail_on_regression_exits_zero_when_only_resolved(tmp_path: pathlib.Path):
    baseline_path = tmp_path / 'baseline.json'
    current_path = tmp_path / 'current.json'
    _write_results(baseline_path, [_outcome('alpha', 'failed')])
    _write_results(current_path, [_outcome('alpha', 'passed')])

    result = testing.CliRunner().invoke(
        cli.main,
        ['compare', '--fail-on-regression', str(baseline_path), str(current_path)],
    )
    assert result.exit_code == 0, result.output


def test_compare_schema_version_mismatch_shows_error(tmp_path: pathlib.Path):
    import json

    baseline_path = tmp_path / 'baseline.json'
    current_path = tmp_path / 'current.json'
    baseline_path.write_text(json.dumps({'version': 999, 'outcomes': []}))
    _write_results(current_path, [_outcome('alpha', 'passed')])

    result = testing.CliRunner().invoke(
        cli.main,
        ['compare', str(baseline_path), str(current_path)],
    )
    assert result.exit_code != 0
    assert 'schema version mismatch' in result.output
