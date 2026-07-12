#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
# noqa: SIZE_OK - one cohesive pipeline edge-case regression matrix.
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Final, NamedTuple, TextIO
from unittest.mock import patch


SKILL_DIR: Final = Path(__file__).resolve().parents[1]
REPO_ROOT: Final = SKILL_DIR.parents[4]
RUNNER: Final = SKILL_DIR / "scripts" / "run_contract_review.py"
VALIDATOR: Final = SKILL_DIR / "scripts" / "validate_pipeline.py"
SRC_ROOT: Final = SKILL_DIR.parents[1]
SUBMISSION_ROOT: Final = SKILL_DIR.parents[2]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import run_contract_review as runner  # noqa: E402


class CommandResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


def run_python(args: list[str], cwd: Path = REPO_ROOT) -> CommandResult:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    return CommandResult(result.returncode, result.stdout, result.stderr)


def run_demo(input_dir: Path, output_dir: Path, run_id: str) -> CommandResult:
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return run_python(
        [
            str(RUNNER),
            "--demo",
            "--run-id",
            run_id,
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
        ]
    )


def make_request(root: Path, run_id: str) -> runner.RunRequest:
    (root / "input").mkdir(parents=True, exist_ok=True)
    (root / "output").mkdir(parents=True, exist_ok=True)
    return runner.RunRequest(
        SKILL_DIR / "fixtures" / "sample_contract_01.md",
        root / "input",
        root / "output",
        run_id,
        "local_only",
        "demo_fixture",
        "not legal advice",
    )


def input_artifact(input_dir: Path, run_id: str) -> Path:
    return input_dir / f"{run_id}--input.md"


def output_artifact(output_dir: Path, run_id: str, name: str) -> Path:
    return output_dir / f"{run_id}--{name}"


class PipelineEdgeTests(unittest.TestCase):
    def test_cli_rejects_input_root_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            root = Path(directory)
            competitor = root / "competitor-input"
            competitor.mkdir()
            input_link = root / "input"
            input_link.symlink_to(competitor, target_is_directory=True)

            result = run_demo(input_link, root / "output", "input-root-link")

            self.assertEqual(result.returncode, 1)
            self.assertTrue(input_link.is_symlink())
            self.assertFalse(input_artifact(competitor, "input-root-link").exists())

    def test_cli_rejects_output_root_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            root = Path(directory)
            competitor = root / "competitor-output"
            competitor.mkdir()
            output_link = root / "output"
            output_link.symlink_to(competitor, target_is_directory=True)

            result = run_demo(root / "input", output_link, "output-root-link")

            self.assertEqual(result.returncode, 1)
            self.assertTrue(output_link.is_symlink())
            self.assertFalse(
                output_artifact(competitor, "output-root-link", "baseline.json").exists()
            )

    def test_retained_submission_runs_have_input_output_pairs(self) -> None:
        input_root = SUBMISSION_ROOT / "input"
        output_root = SUBMISSION_ROOT / "output"
        output_runs = sorted(path for path in output_root.iterdir() if path.is_dir())

        self.assertGreater(len(output_runs), 0)
        for output_run in output_runs:
            run_id = output_run.name
            self.assertTrue((input_root / run_id / "input.md").is_file(), run_id)
            self.assertFalse((output_run / "input.md").exists(), run_id)
            for name in ("baseline.json", "review.md", "report.md", "state.md"):
                self.assertTrue((output_run / name).is_file(), f"{run_id}/{name}")

    def test_demo_run_writes_input_record_outside_output_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            input_dir = Path(directory) / "input"
            output_dir = Path(directory) / "output"

            result = run_demo(input_dir, output_dir, "paired-layout")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(input_artifact(input_dir, "paired-layout").exists())
            self.assertFalse(output_artifact(output_dir, "paired-layout", "input.md").exists())

    def test_owned_artifact_write_does_not_depend_on_fdopen(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            root = Path(directory)
            directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with patch.object(
                    runner.os,
                    "fdopen",
                    side_effect=OSError("forced wrapper failure"),
                ):
                    runner.write_owned_text(directory_fd, "artifact.md", "complete\n")
            finally:
                os.close(directory_fd)

            self.assertEqual(
                (root / "artifact.md").read_text(encoding="utf-8"),
                "complete\n",
            )

    def test_partial_raw_write_is_retained_and_retry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            root = Path(directory)
            request = make_request(root, "partial-write")
            artifact = input_artifact(request.input_dir, request.run_id)
            real_write = os.write
            write_count = 0

            def fail_after_prefix(descriptor: int, payload: bytes) -> int:
                nonlocal write_count
                write_count += 1
                if write_count == 1:
                    return real_write(descriptor, payload[:1])
                raise OSError("forced raw write failure")

            descriptors_before = len(os.listdir("/dev/fd"))
            with patch.object(runner.os, "write", side_effect=fail_after_prefix):
                with self.assertRaisesRegex(OSError, "forced raw write failure"):
                    runner.write_run(request)
            descriptors_after = len(os.listdir("/dev/fd"))

            self.assertEqual(artifact.read_bytes(), b"#")
            self.assertEqual(descriptors_after, descriptors_before)
            with self.assertRaises(runner.UsageError):
                runner.write_run(request)
            self.assertEqual(artifact.read_bytes(), b"#")

    def test_existing_run_directory_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            input_dir = Path(directory) / "input"
            output_dir = Path(directory) / "output"
            run_dir = output_dir / "same-run"
            run_dir.mkdir(parents=True)
            sentinel = run_dir / "sentinel.txt"
            sentinel.write_text("keep me", encoding="utf-8")

            result = run_demo(input_dir, output_dir, "same-run")

            self.assertEqual(result.returncode, 2)
            self.assertIn("run already exists", result.stdout)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep me")
            self.assertFalse((run_dir / "baseline.json").exists())
            self.assertFalse((input_dir / "same-run").exists())

    def test_existing_input_run_directory_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            input_dir = Path(directory) / "input"
            output_dir = Path(directory) / "output"
            run_dir = input_dir / "same-run"
            run_dir.mkdir(parents=True)
            sentinel = run_dir / "sentinel.txt"
            sentinel.write_text("keep me", encoding="utf-8")

            result = run_demo(input_dir, output_dir, "same-run")

            self.assertEqual(result.returncode, 2)
            self.assertIn("run already exists", result.stdout)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep me")
            self.assertFalse((run_dir / "input.md").exists())
            self.assertFalse((output_dir / "same-run").exists())

    def test_cleanup_preserves_competitor_run_created_after_precheck(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            root = Path(directory)
            request = make_request(root, "same-run")
            competitor = input_artifact(request.input_dir, request.run_id)
            competitor_text = "competitor-owned input\n"
            real_write_input = runner.write_input

            def collide_after_precheck(
                run_request: runner.RunRequest,
                directory_fd: int,
            ) -> None:
                competitor.write_text(competitor_text, encoding="utf-8")
                real_write_input(run_request, directory_fd)

            with patch.object(runner, "write_input", collide_after_precheck):
                with self.assertRaises(FileExistsError):
                    runner.write_run(request)

            self.assertEqual(competitor.read_text(encoding="utf-8"), competitor_text)

    def test_cleanup_preserves_exact_name_competitor_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            root = Path(directory)
            input_dir = root / "input"
            output_dir = root / "output"
            competitor = input_artifact(input_dir, "artifact-race")
            competitor_text = "competitor-owned input\n"
            request = runner.RunRequest(
                SKILL_DIR / "fixtures" / "sample_contract_01.md",
                input_dir,
                output_dir,
                "artifact-race",
                "local_only",
                "demo_fixture",
                "not legal advice",
            )
            input_dir.mkdir()
            output_dir.mkdir()
            real_write_input = runner.write_input

            def collide_before_write(
                run_request: runner.RunRequest,
                directory_fd: int,
            ) -> None:
                competitor.write_text(competitor_text, encoding="utf-8")
                try:
                    real_write_input(run_request, directory_fd)
                except FileExistsError:
                    raise OSError("forced operational write failure") from None
                raise OSError("forced operational write failure")

            with patch.object(runner, "write_input", collide_before_write):
                with self.assertRaisesRegex(
                    OSError, "forced operational write failure"
                ):
                    runner.write_run(request)

            self.assertEqual(competitor.read_text(encoding="utf-8"), competitor_text)

            symlink_request = make_request(root, "symlink-race")
            symlink_artifact = input_artifact(input_dir, symlink_request.run_id)
            symlink_target = root / "competitor-target.md"
            symlink_target.write_text(competitor_text, encoding="utf-8")

            def collide_with_symlink(
                run_request: runner.RunRequest, directory_fd: int
            ) -> None:
                symlink_artifact.symlink_to(symlink_target)
                try:
                    real_write_input(run_request, directory_fd)
                except FileExistsError:
                    raise OSError("forced symlink collision") from None

            with patch.object(runner, "write_input", collide_with_symlink):
                with self.assertRaisesRegex(OSError, "forced symlink collision"):
                    runner.write_run(symlink_request)

            self.assertTrue(symlink_artifact.is_symlink())
            self.assertEqual(
                symlink_target.read_text(encoding="utf-8"), competitor_text
            )

    def test_failure_never_unlinks_replacement_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            root = Path(directory)
            request = make_request(root, "artifact-swap")
            input_artifact = globals()["input_artifact"](request.input_dir, request.run_id)
            competitor_text = "replacement-owned input\n"

            def fail_after_swap(
                _baseline: runner.SafeBaseline,
                _directory_fd: int,
                _run_id: str,
            ) -> None:
                input_artifact.unlink()
                input_artifact.write_text(competitor_text, encoding="utf-8")
                raise OSError("forced after artifact swap")

            with patch.object(runner, "write_review", fail_after_swap):
                with self.assertRaisesRegex(OSError, "forced after artifact swap"):
                    runner.write_run(request)

            self.assertEqual(
                input_artifact.read_text(encoding="utf-8"), competitor_text
            )

    def test_failure_never_removes_replacement_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            root = Path(directory)
            request = make_request(root, "directory-swap")
            output_run = request.output_dir / request.run_id
            output_run.mkdir(parents=True)
            replacement_inode = output_run.stat().st_ino

            with self.assertRaises(runner.UsageError):
                runner.write_run(request)

            self.assertTrue(output_run.is_dir())
            self.assertEqual(output_run.stat().st_ino, replacement_inode)

    def test_directory_symlink_swap_cannot_redirect_artifact_write(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            root = Path(directory)
            request = make_request(root, "parent-symlink-swap")
            original_input = root / "original-input"
            competitor_dir = root / "competitor-dir"
            competitor_dir.mkdir()
            real_sanitize = runner.sanitize_baseline

            def swap_parent_directory(
                baseline: runner.Baseline,
            ) -> runner.SafeBaseline:
                safe_baseline = real_sanitize(baseline)
                request.input_dir.rename(original_input)
                request.input_dir.symlink_to(competitor_dir, target_is_directory=True)
                return safe_baseline

            with patch.object(runner, "sanitize_baseline", swap_parent_directory):
                runner.write_run(request)

            self.assertTrue(request.input_dir.is_symlink())
            self.assertFalse(input_artifact(competitor_dir, request.run_id).exists())
            self.assertTrue(input_artifact(original_input, request.run_id).exists())

    def test_learning_creation_collision_preserves_competitor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            root = Path(directory)
            request = make_request(root, "learning-race")
            memory = request.output_dir / "_learnings.md"
            competitor_text = "competitor-owned learning\n"
            real_append_learning = runner.append_learning

            def collide_before_create(
                run_request: runner.RunRequest,
                finding_count: int,
                learning_handle: TextIO | None,
                output_directory_fd: int,
            ) -> None:
                memory.write_text(competitor_text, encoding="utf-8")
                real_append_learning(
                    run_request,
                    finding_count,
                    learning_handle,
                    output_directory_fd,
                )

            with patch.object(runner, "append_learning", collide_before_create):
                with self.assertRaises(FileExistsError):
                    runner.write_run(request)

            self.assertEqual(memory.read_text(encoding="utf-8"), competitor_text)

    def test_learning_symlink_never_mutates_competitor_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            root = Path(directory)
            competitor_text = "competitor-owned learning\n"
            symlink_request = make_request(root, "learning-symlink")
            symlink_request.output_dir.mkdir(parents=True, exist_ok=True)
            symlink_memory = symlink_request.output_dir / "_learnings.md"
            symlink_target = root / "competitor-learning.md"
            symlink_target.write_text(competitor_text, encoding="utf-8")
            symlink_memory.symlink_to(symlink_target)

            descriptors_before = len(os.listdir("/dev/fd"))
            for _attempt in range(25):
                with self.assertRaises(OSError):
                    runner.write_run(symlink_request)
            descriptors_after = len(os.listdir("/dev/fd"))

            self.assertTrue(symlink_memory.is_symlink())
            self.assertEqual(
                symlink_target.read_text(encoding="utf-8"), competitor_text
            )
            self.assertEqual(descriptors_after, descriptors_before)

            hardlink_root = root / "hardlink"
            hardlink_request = make_request(hardlink_root, "learning-hardlink")
            hardlink_request.output_dir.mkdir(parents=True, exist_ok=True)
            hardlink_target = root / "competitor-hardlink.md"
            hardlink_target.write_text(competitor_text, encoding="utf-8")
            os.link(
                hardlink_target,
                hardlink_request.output_dir / "_learnings.md",
            )

            with self.assertRaisesRegex(OSError, "singly linked regular file"):
                runner.write_run(hardlink_request)

            self.assertEqual(
                hardlink_target.read_text(encoding="utf-8"), competitor_text
            )

            fdopen_root = root / "fdopen"
            fdopen_request = make_request(fdopen_root, "fdopen-failure")
            descriptors_before = len(os.listdir("/dev/fd"))
            with patch.object(runner.os, "fdopen", side_effect=OSError("fdopen")):
                with self.assertRaisesRegex(OSError, "fdopen"):
                    runner.write_run(fdopen_request)
            descriptors_after = len(os.listdir("/dev/fd"))
            self.assertEqual(descriptors_after, descriptors_before)
            memory_template = SKILL_DIR / "templates" / "learnings_TEMPLATE.md"
            (fdopen_request.output_dir / "_learnings.md").write_text(
                memory_template.read_text(encoding="utf-8"), encoding="utf-8"
            )
            reserve_request = fdopen_request._replace(run_id="reserve-fdopen")
            with patch.object(runner.os, "fdopen", side_effect=OSError("reserve")):
                with self.assertRaisesRegex(OSError, "reserve"):
                    runner.write_run(reserve_request)
            self.assertEqual(len(os.listdir("/dev/fd")), descriptors_before)

    def test_output_root_swap_cannot_redirect_learning_creation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            root = Path(directory)
            request = make_request(root, "learning-parent-swap")
            original_output = root / "original-output"
            competitor_output = root / "competitor-output"
            competitor_output.mkdir()
            real_write_state = runner.write_state

            def swap_output_root(
                paths: runner.ArtifactPaths,
                run_request: runner.RunRequest,
                directory_fd: int,
            ) -> None:
                real_write_state(paths, run_request, directory_fd)
                run_request.output_dir.rename(original_output)
                run_request.output_dir.symlink_to(
                    competitor_output, target_is_directory=True
                )

            with patch.object(runner, "write_state", swap_output_root):
                runner.write_run(request)

            self.assertTrue(request.output_dir.is_symlink())
            self.assertFalse((competitor_output / "_learnings.md").exists())
            self.assertTrue((original_output / "_learnings.md").is_file())

    def test_missing_input_returns_exit_2_without_partial_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            input_dir = Path(directory) / "input"
            output_dir = Path(directory) / "out"
            missing = Path(directory) / "missing-contract.md"

            result = run_python(
                [
                    str(RUNNER),
                    "--input",
                    str(missing),
                    "--run-id",
                    "missing-input",
                    "--input-dir",
                    str(input_dir),
                    "--output-dir",
                    str(output_dir),
                ]
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("계약서 파일을 찾을 수 없습니다", result.stdout)
            self.assertFalse((input_dir / "missing-input").exists())
            self.assertFalse((output_dir / "missing-input").exists())

    def test_role_artifacts_do_not_copy_raw_snippets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            input_dir = Path(directory) / "input"
            output_dir = Path(directory) / "output"
            result = run_demo(input_dir, output_dir, "snippet-safe")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            baseline = json.loads(output_artifact(output_dir, "snippet-safe", "baseline.json").read_text(encoding="utf-8"))
            review = output_artifact(output_dir, "snippet-safe", "review.md").read_text(encoding="utf-8")
            report = output_artifact(output_dir, "snippet-safe", "report.md").read_text(encoding="utf-8")

            snippets = [finding["snippet"] for finding in baseline["findings"] if finding["snippet"]]
            self.assertGreater(len(snippets), 0)
            for snippet in snippets:
                self.assertNotIn(snippet, review)
                self.assertNotIn(snippet, report)

    def test_learning_memory_preserves_existing_content_and_appends_one_row(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            input_dir = Path(directory) / "input"
            output_dir = Path(directory) / "output"
            memory = output_dir / "_learnings.md"
            output_dir.mkdir()
            template = (SKILL_DIR / "templates" / "learnings_TEMPLATE.md").read_text(encoding="utf-8")
            seed = template + "\n<!-- marker: preserve existing learning memory -->\n"
            memory.write_text(seed, encoding="utf-8")

            result = run_demo(input_dir, output_dir, "learn-once")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            updated = memory.read_text(encoding="utf-8")
            self.assertTrue(updated.startswith(seed))
            self.assertEqual(updated.count("| learn-once |"), 1)
            self.assertIn("local pipeline run appended after reread", updated)

    def test_validator_can_run_twice_in_same_output_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="musinsa-edge-") as directory:
            input_dir = Path(directory) / "input"
            output_dir = Path(directory) / "output"

            first = run_python(
                [str(VALIDATOR), "--skill-dir", str(SKILL_DIR), "--input-dir", str(input_dir), "--output-dir", str(output_dir)]
            )
            second = run_python(
                [str(VALIDATOR), "--skill-dir", str(SKILL_DIR), "--input-dir", str(input_dir), "--output-dir", str(output_dir)]
            )

            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn("pipeline validation passed", first.stdout)
            self.assertIn("pipeline validation passed", second.stdout)

    def test_validator_negative_samples_are_rejected(self) -> None:
        for sample in ("missing-disclaimer", "forbidden-network", "bad-baseline"):
            with self.subTest(sample=sample):
                result = run_python(
                    [
                        str(VALIDATOR),
                        "--skill-dir",
                        str(SKILL_DIR),
                        "--input-dir",
                        ".",
                        "--output-dir",
                        ".",
                        "--negative-sample",
                        sample,
                    ]
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f"negative sample rejected: {sample}", result.stdout)

    def test_no_bytecode_cache_is_created_under_submission_src(self) -> None:
        caches = [path for path in SRC_ROOT.rglob("*") if path.name == "__pycache__" or path.suffix == ".pyc"]

        self.assertEqual(caches, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
