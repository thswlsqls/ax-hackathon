from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SUBMISSION_INPUT = PLUGIN_ROOT / "input"
SUBMISSION_OUTPUT = PLUGIN_ROOT / "output"
WRAPPER = PLUGIN_ROOT / "src" / "bin" / "samil_independence_run.py"
PYTHON = sys.executable


def reset_submission_artifacts(run_ids: tuple[str, ...]) -> None:
    for run_id in run_ids:
        shutil.rmtree(SUBMISSION_INPUT / run_id, ignore_errors=True)
        shutil.rmtree(SUBMISSION_OUTPUT / run_id, ignore_errors=True)


def base_wrapper_command(run_id: str) -> list[str]:
    return [
        PYTHON,
        os.fspath(WRAPPER),
        "--audit-clients",
        "src/examples/audit_clients.csv",
        "--non-audit-services",
        "src/examples/non_audit_services.csv",
        "--rules",
        "src/examples/independence_rules.json",
        "--run-id",
        run_id,
    ]


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=PLUGIN_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )


def test_wrapper_rejects_duplicate_run_id_before_creating_artifacts(
    tmp_path: Path,
) -> None:
    # Given: wrapper-only run id flags disagree in the same invocation.
    _ = tmp_path
    reset_submission_artifacts(("first-run", "second-run"))

    # When: the wrapper receives duplicate run ids.
    result = run_command(
        [
            *base_wrapper_command("first-run"),
            "--run-id",
            "second-run",
            "--input-dir",
            os.fspath(SUBMISSION_INPUT),
            "--output-dir",
            os.fspath(SUBMISSION_OUTPUT),
        ]
    )

    # Then: the ambiguous invocation fails before any run directory is created.
    assert result.returncode == 1
    assert "duplicate option: --run-id" in result.stderr
    assert not (SUBMISSION_INPUT / "first-run").exists()
    assert not (SUBMISSION_INPUT / "second-run").exists()
    assert not (SUBMISSION_OUTPUT / "first-run").exists()
    assert not (SUBMISSION_OUTPUT / "second-run").exists()


def test_wrapper_rejects_missing_wrapper_directory_value(tmp_path: Path) -> None:
    # Given: a wrapper-only option is present without a value.
    _ = tmp_path
    reset_submission_artifacts(("missing-output",))

    # When: the wrapper parses the incomplete invocation.
    result = run_command([*base_wrapper_command("missing-output"), "--output-dir"])

    # Then: the boundary error is explicit and no default run directory is used.
    assert result.returncode == 1
    assert "missing value for --output-dir" in result.stderr
    assert not (SUBMISSION_OUTPUT / "missing-output").exists()


def test_wrapper_rejects_duplicate_input_dir_before_creating_artifacts(
    tmp_path: Path,
) -> None:
    # Given: wrapper-only input directory flags disagree in the same invocation.
    first_input_dir = tmp_path / "input-a"
    second_input_dir = tmp_path / "input-b"
    reset_submission_artifacts(("duplicate-input",))

    # When: the wrapper receives duplicate input roots.
    result = run_command(
        [
            *base_wrapper_command("duplicate-input"),
            "--input-dir",
            os.fspath(first_input_dir),
            "--input-dir",
            os.fspath(second_input_dir),
            "--output-dir",
            os.fspath(SUBMISSION_OUTPUT),
        ]
    )

    # Then: the ambiguous invocation fails before any run directory is created.
    assert result.returncode == 1
    assert "duplicate option: --input-dir" in result.stderr
    assert not (first_input_dir / "duplicate-input").exists()
    assert not (second_input_dir / "duplicate-input").exists()
    assert not (SUBMISSION_OUTPUT / "duplicate-input").exists()
