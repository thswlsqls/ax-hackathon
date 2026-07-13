#!/usr/bin/env python3
"""Exercise the cohesive end-to-end pipeline lifecycle matrix.

# noqa: SIZE_OK - splitting the matrix would duplicate direct-script setup.
"""
import contextlib
import io
import json
import signal
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import run_pipeline as rp  # noqa: E402
from io_contract import SubmissionIOTestCase  # noqa: E402


class RunPipelineTest(SubmissionIOTestCase):
    def test_pipeline_run_writes_state_artifacts_checklist_and_one_memory_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"

            code = rp.run_cli([
                "--run-id",
                "qa-fixed",
                "--input-dir",
                str(input_dir),
                "--output-dir",
                str(output_dir),
            ])

            run_dir = output_dir / "runs" / "qa-fixed"
            input_run_dir = input_dir / "qa-fixed"
            self.assertEqual(code, 0)
            self.assertTrue((input_run_dir / "incidents.json").exists())
            self.assertTrue((input_run_dir / "stability-config.json").exists())
            for name in ("analysis.json", "chaos.json", "scenario-checklist.md", "state.json"):
                self.assertTrue((run_dir / name).exists(), msg=name)
                self.assertFalse((input_run_dir / name).exists(), msg=name)
            self.assertFalse((run_dir / "incidents.json").exists())
            self.assertFalse((run_dir / "stability-config.json").exists())

            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "succeeded")
            self.assertEqual(state["run_id"], "qa-fixed")
            self.assertEqual(state["input_artifacts"]["input"], str(input_run_dir / "incidents.json"))
            self.assertEqual(state["input_artifacts"]["config"], str(input_run_dir / "stability-config.json"))
            self.assertEqual(state["analysis_summary"]["incident_total"], 5)
            self.assertEqual(state["chaos_summary"]["scenario_total"], 3)

            checklist = (run_dir / "scenario-checklist.md").read_text(encoding="utf-8")
            for token in ("[사실]", "[해석]", "[학습]", "external_broker_dependency"):
                self.assertIn(token, checklist)
            self.assertNotRegex(checklist, r"TODO|TBD|<pattern>|\\{slug\\}")

            memory = (output_dir / "_learnings.md").read_text(encoding="utf-8")
            self.assertEqual(memory.count("run=qa-fixed status=succeeded"), 1)

        with tempfile.TemporaryDirectory(dir="/tmp") as alias_tmp:
            alias_root = Path(alias_tmp)
            canonical_root = alias_root.resolve()
            if alias_root != canonical_root:
                exit_codes = []
                for label, root in (("alias", alias_root), ("canonical", canonical_root)):
                    exit_codes.append(rp.run_cli([
                        "--run-id",
                        f"qa-{label}",
                        "--input-dir",
                        str(root / f"input-{label}"),
                        "--output-dir",
                        str(root / f"output-{label}"),
                    ]))
                self.assertEqual(exit_codes, [0, 0])

    def test_existing_run_id_fails_before_memory_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            args = ["--run-id", "qa-fixed", "--input-dir", str(input_dir), "--output-dir", str(output_dir)]
            self.assertEqual(rp.run_cli(args), 0)
            before = (output_dir / "_learnings.md").read_text(encoding="utf-8")
            state_before = (output_dir / "runs" / "qa-fixed" / "state.json").read_text(encoding="utf-8")
            input_before = (input_dir / "qa-fixed" / "incidents.json").read_text(encoding="utf-8")

            code = rp.run_cli(args)

            self.assertNotEqual(code, 0)
            after = (output_dir / "_learnings.md").read_text(encoding="utf-8")
            state_after = (output_dir / "runs" / "qa-fixed" / "state.json").read_text(encoding="utf-8")
            input_after = (input_dir / "qa-fixed" / "incidents.json").read_text(encoding="utf-8")
            self.assertEqual(before, after)
            self.assertEqual(state_before, state_after)
            self.assertEqual(input_before, input_after)

    def test_second_run_selects_first_succeeded_memory_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            common = ["--skip-chaos", "--input-dir", str(input_dir), "--output-dir", str(output_dir)]

            self.assertEqual(rp.run_cli(["--run-id", "qa-first", *common]), 0)
            self.assertEqual(rp.run_cli(["--run-id", "qa-second", *common]), 0)

            checklist = (output_dir / "runs" / "qa-second" / "scenario-checklist.md").read_text(encoding="utf-8")
            self.assertIn("run=qa-first status=succeeded", checklist)
            self.assertNotIn("No prior matching lessons.", checklist)

    def test_one_sided_run_collisions_preserve_existing_bytes(self):
        for collision in ("input", "output"):
            with self.subTest(collision=collision), tempfile.TemporaryDirectory() as tmp:
                input_dir = Path(tmp) / "input"
                output_dir = Path(tmp) / "output"
                existing = (
                    input_dir / "qa-collision"
                    if collision == "input"
                    else output_dir / "runs" / "qa-collision"
                )
                existing.mkdir(parents=True)
                marker = existing / "marker.txt"
                marker.write_text("preserve", encoding="utf-8")

                code = rp.run_cli([
                    "--run-id",
                    "qa-collision",
                    "--input-dir",
                    str(input_dir),
                    "--output-dir",
                    str(output_dir),
                ])

                self.assertNotEqual(code, 0)
                self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")
                other = (
                    output_dir / "runs" / "qa-collision"
                    if collision == "input"
                    else input_dir / "qa-collision"
                )
                self.assertFalse(other.exists())

    def test_path_like_run_id_is_rejected_before_writing_outside_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            output_dir = root / "output"

            code = rp.run_cli([
                "--run-id",
                "../escape",
                "--input-dir",
                str(input_dir),
                "--output-dir",
                str(output_dir),
            ])

            self.assertNotEqual(code, 0)
            self.assertFalse((root / "escape").exists())
            self.assertFalse((output_dir / "runs" / ".." / "escape").exists())
            self.assertFalse((input_dir / ".." / "escape").exists())

    def test_unsafe_run_id_variants_are_rejected_without_creating_roots(self):
        unsafe_ids = (".hidden", "a..b", "slash/name", "control\nname", "", "a" * 129)
        for run_id in unsafe_ids:
            with self.subTest(run_id=run_id), tempfile.TemporaryDirectory() as tmp:
                input_dir = Path(tmp) / "input"
                output_dir = Path(tmp) / "output"

                code = rp.run_cli([
                    "--run-id",
                    run_id,
                    "--input-dir",
                    str(input_dir),
                    "--output-dir",
                    str(output_dir),
                ])

                self.assertNotEqual(code, 0)
                self.assertFalse(input_dir.exists())
                self.assertFalse(output_dir.exists())

    def test_missing_input_marks_failed_without_success_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            memory_path = output_dir / "_learnings.md"
            rp.pm.ensure_memory(memory_path)
            memory_before = memory_path.read_bytes()
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                code = rp.run_cli([
                    "--input",
                    str(Path(tmp) / "missing.json"),
                    "--run-id",
                    "qa-bad",
                    "--input-dir",
                    str(input_dir),
                    "--output-dir",
                    str(output_dir),
                ])

            self.assertNotEqual(code, 0)
            self.assertFalse((input_dir / "qa-bad").exists())
            self.assertFalse((output_dir / "runs" / "qa-bad").exists())
            self.assertEqual(memory_path.read_bytes(), memory_before)
            self.assertEqual(stderr.getvalue(), "pipeline execution failed\n")
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertNotIn(str(Path(tmp)), stderr.getvalue())

    def test_malformed_json_input_marks_failed_without_success_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            bad_input = Path(tmp) / "broken.json"
            bad_input.write_text("{broken", encoding="utf-8")
            memory_path = output_dir / "_learnings.md"
            rp.pm.ensure_memory(memory_path)
            memory_before = memory_path.read_bytes()
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                code = rp.run_cli([
                    "--input",
                    str(bad_input),
                    "--run-id",
                    "qa-malformed",
                    "--input-dir",
                    str(input_dir),
                    "--output-dir",
                    str(output_dir),
                ])

            self.assertNotEqual(code, 0)
            self.assertFalse((input_dir / "qa-malformed").exists())
            self.assertFalse((output_dir / "runs" / "qa-malformed").exists())
            self.assertEqual(memory_path.read_bytes(), memory_before)
            self.assertEqual(stderr.getvalue(), "pipeline execution failed\n")
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertNotIn(str(Path(tmp)), stderr.getvalue())

    def test_empty_incident_input_succeeds_with_empty_analysis_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "output"
            input_dir = Path(tmp) / "input"
            empty_input = Path(tmp) / "empty.json"
            empty_input.write_text(json.dumps({
                "meta": {"subject": "empty fixture"},
                "annual_counts": {"basis": "unit-test", "source": "fixture", "counts": {}},
                "incidents": [],
            }), encoding="utf-8")

            code = rp.run_cli([
                "--input",
                str(empty_input),
                "--run-id",
                "qa-empty",
                "--skip-chaos",
                "--input-dir",
                str(input_dir),
                "--output-dir",
                str(output_dir),
            ])

            self.assertEqual(code, 0)
            run_dir = output_dir / "runs" / "qa-empty"
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["analysis_summary"], {
                "incident_total": 0,
                "scenario_total": 0,
                "dominant_pattern": None,
            })
            checklist = (run_dir / "scenario-checklist.md").read_text(encoding="utf-8")
            self.assertIn("분석 사건: 0건", checklist)
            self.assertIn("No prior matching lessons.", checklist)
            memory = (output_dir / "_learnings.md").read_text(encoding="utf-8")
            self.assertIn("run=qa-empty status=succeeded incidents=0 scenarios=0", memory)
            self.assertIn("dominant=None", memory)

    def test_skip_chaos_records_skipped_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"

            code = rp.run_cli([
                "--run-id",
                "qa-skip",
                "--skip-chaos",
                "--input-dir",
                str(input_dir),
                "--output-dir",
                str(output_dir),
            ])

            self.assertEqual(code, 0)
            state = json.loads((output_dir / "runs" / "qa-skip" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["chaos_summary"]["status"], "skipped")
            self.assertFalse((output_dir / "runs" / "qa-skip" / "chaos.json").exists())

    def test_cli_timeout_and_early_interruption_are_controlled_and_nonmutating(self):
        cases = ((TimeoutError(), 124, "pipeline execution timed out\n"),)
        for failure, expected_code, expected_error in cases:
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as tmp:
                input_dir = Path(tmp) / "input"
                output_dir = Path(tmp) / "output"
                stderr = io.StringIO()
                handler_before = signal.getsignal(signal.SIGALRM)
                timer_before = signal.getitimer(signal.ITIMER_REAL)

                with mock.patch.object(rp, "run_pipeline", side_effect=failure):
                    with contextlib.redirect_stderr(stderr):
                        code = rp.run_cli([
                            "--run-id",
                            "qa-stop",
                            "--input-dir",
                            str(input_dir),
                            "--output-dir",
                            str(output_dir),
                        ])

                self.assertEqual(code, expected_code)
                self.assertEqual(stderr.getvalue(), expected_error)
                self.assertNotIn("Traceback", stderr.getvalue())
                self.assertFalse(input_dir.exists())
                self.assertFalse(output_dir.exists())
                self.assertIs(signal.getsignal(signal.SIGALRM), handler_before)
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL), timer_before)

        failure = KeyboardInterrupt("early stop")
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            stderr = io.StringIO()

            with mock.patch.object(rp, "run_pipeline", side_effect=failure):
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(KeyboardInterrupt) as raised:
                        rp.run_cli([
                            "--run-id", "qa-interrupt", "--input-dir", str(input_dir),
                            "--output-dir", str(output_dir),
                        ])

            self.assertIs(raised.exception, failure)
            self.assertEqual(stderr.getvalue(), "pipeline execution interrupted\n")
            self.assertFalse(input_dir.exists())
            self.assertFalse(output_dir.exists())

        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            stderr = io.StringIO()

            with mock.patch.object(rp, "run_pipeline", side_effect=OSError("private path")):
                with contextlib.redirect_stderr(stderr):
                    code = rp.run_cli([
                        "--run-id", "qa-oserror", "--input-dir", str(input_dir),
                        "--output-dir", str(output_dir),
                    ])

            self.assertEqual(code, 1)
            self.assertEqual(stderr.getvalue(), "pipeline execution failed\n")
            self.assertFalse(input_dir.exists())
            self.assertFalse(output_dir.exists())

        failure = TypeError("programming defect")
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(rp, "run_pipeline", side_effect=failure):
                with self.assertRaises(TypeError) as raised:
                    rp.run_cli([
                        "--run-id", "qa-typeerror",
                        "--input-dir", str(Path(tmp) / "input"),
                        "--output-dir", str(Path(tmp) / "output"),
                    ])

            self.assertIs(raised.exception, failure)

        failure = SystemExit(77)
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"

            with mock.patch.object(rp, "run_pipeline", side_effect=failure):
                with self.assertRaises(SystemExit) as raised:
                    rp.run_cli([
                        "--run-id", "qa-system-exit",
                        "--input-dir", str(input_dir),
                        "--output-dir", str(output_dir),
                    ])

            self.assertIs(raised.exception, failure)
            self.assertFalse(input_dir.exists())
            self.assertFalse(output_dir.exists())

    def test_interruption_after_snapshots_marks_failed_without_success_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            stderr = io.StringIO()

            failure = KeyboardInterrupt("stop after snapshots")
            with mock.patch.object(rp, "_render_checklist", side_effect=failure):
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(KeyboardInterrupt) as raised:
                        rp.run_cli([
                            "--run-id",
                            "qa-interrupted",
                            "--input-dir",
                            str(input_dir),
                            "--output-dir",
                            str(output_dir),
                        ])

            run_dir = output_dir / "runs" / "qa-interrupted"
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            self.assertIs(raised.exception, failure)
            self.assertEqual(stderr.getvalue(), "pipeline execution interrupted\n")
            self.assertEqual(state["status"], "failed")
            self.assertTrue((input_dir / "qa-interrupted" / "incidents.json").exists())
            memory = (output_dir / "_learnings.md").read_text(encoding="utf-8")
            self.assertNotIn("run=qa-interrupted status=succeeded", memory)

        failure = GeneratorExit("consumer closed")
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            stderr = io.StringIO()

            with mock.patch.object(rp, "_render_checklist", side_effect=failure):
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(GeneratorExit) as raised:
                        rp.run_cli([
                            "--run-id", "qa-generator-exit",
                            "--input-dir", str(input_dir),
                            "--output-dir", str(output_dir),
                        ])

            state_path = output_dir / "runs" / "qa-generator-exit" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIs(raised.exception, failure)
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["error"], "pipeline execution terminated")
            self.assertEqual(stderr.getvalue(), "pipeline execution terminated\n")
            self.assertNotIn("consumer closed", state_path.read_text(encoding="utf-8"))

        failure = SystemExit(78)
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            stderr = io.StringIO()

            with mock.patch.object(rp, "_render_checklist", side_effect=failure):
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        rp.run_cli([
                            "--run-id", "qa-late-system-exit",
                            "--input-dir", str(input_dir),
                            "--output-dir", str(output_dir),
                        ])

            state_path = output_dir / "runs" / "qa-late-system-exit" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIs(raised.exception, failure)
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["error"], "pipeline execution terminated")
            self.assertEqual(stderr.getvalue(), "pipeline execution terminated\n")

    def test_precommit_terminations_mark_failed_and_preserve_identity(self):
        terminations = (
            KeyboardInterrupt("pre-commit interrupt"),
            SystemExit(79),
            GeneratorExit("pre-commit close"),
        )
        for index, termination in enumerate(terminations):
            with self.subTest(termination=type(termination).__name__), tempfile.TemporaryDirectory() as tmp:
                input_dir = Path(tmp) / "input"
                output_dir = Path(tmp) / "output"
                run_id = f"qa-precommit-{index}"
                stderr = io.StringIO()

                with mock.patch.object(rp.pm, "append_learning", side_effect=termination):
                    with contextlib.redirect_stderr(stderr):
                        with self.assertRaises(type(termination)) as raised:
                            rp.run_cli([
                                "--run-id", run_id, "--input-dir", str(input_dir),
                                "--output-dir", str(output_dir),
                            ])

                state_path = output_dir / "runs" / run_id / "state.json"
                state = json.loads(state_path.read_text(encoding="utf-8"))
                memory = (output_dir / "_learnings.md").read_text(encoding="utf-8")
                self.assertIs(raised.exception, termination)
                self.assertEqual(state["status"], "failed")
                self.assertNotIn(f"run={run_id} status=succeeded", memory)
                expected = "interrupted" if isinstance(termination, KeyboardInterrupt) else "terminated"
                self.assertEqual(state["error"], f"pipeline execution {expected}")
                self.assertEqual(stderr.getvalue(), f"pipeline execution {expected}\n")

    def test_post_replace_terminations_preserve_succeeded_state_and_identity(self):
        terminations = (
            KeyboardInterrupt("committed interrupt"),
            SystemExit(80),
            GeneratorExit("committed close"),
        )
        for index, termination in enumerate(terminations):
            with self.subTest(termination=type(termination).__name__), tempfile.TemporaryDirectory() as tmp:
                input_dir = Path(tmp) / "input"
                output_dir = Path(tmp) / "output"
                run_id = f"qa-committed-{index}"
                real_replace = rp.sf.os.replace
                real_fsync = rp.sf.os.fsync
                learning_replacements = 0
                terminate_next_fsync = False
                stderr = io.StringIO()

                def track_learning_replace(source, destination, *args, **kwargs):
                    nonlocal learning_replacements, terminate_next_fsync
                    result = real_replace(source, destination, *args, **kwargs)
                    if destination == "_learnings.md":
                        learning_replacements += 1
                        terminate_next_fsync = learning_replacements == 2
                    return result

                def terminate_after_commit(descriptor):
                    nonlocal terminate_next_fsync
                    if terminate_next_fsync:
                        terminate_next_fsync = False
                        raise termination
                    return real_fsync(descriptor)

                with mock.patch.object(rp.sf.os, "replace", side_effect=track_learning_replace):
                    with mock.patch.object(rp.sf.os, "fsync", side_effect=terminate_after_commit):
                        with contextlib.redirect_stderr(stderr):
                            with self.assertRaises(type(termination)) as raised:
                                rp.run_cli([
                                    "--run-id", run_id, "--input-dir", str(input_dir),
                                    "--output-dir", str(output_dir),
                                ])

                state = json.loads(
                    (output_dir / "runs" / run_id / "state.json").read_text(encoding="utf-8")
                )
                memory_lines = (output_dir / "_learnings.md").read_text(encoding="utf-8").splitlines()
                learning = rp._success_memory_line(
                    run_id, state["analysis_summary"], state["chaos_summary"]
                )
                self.assertIs(raised.exception, termination)
                self.assertEqual(learning_replacements, 2)
                self.assertEqual(state["status"], "succeeded")
                self.assertEqual(memory_lines.count(f"## §0 Run tracking {learning}"), 1)
                self.assertEqual(stderr.getvalue(), "")

    def test_memory_append_failure_marks_terminal_failed_without_success_learning(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            run_dir = output_dir / "runs" / "qa-memory-failure"
            stderr = io.StringIO()

            def fail_append(*_args):
                raise rp.pm.MemoryEntryError("private memory detail")

            try:
                with mock.patch.object(rp.pm, "append_learning", side_effect=fail_append):
                    with contextlib.redirect_stderr(stderr):
                        code = rp.run_cli([
                            "--run-id", "qa-memory-failure",
                            "--input-dir", str(input_dir),
                            "--output-dir", str(output_dir),
                        ])
            except rp.pm.MemoryEntryError:
                code = None

            state_text = (run_dir / "state.json").read_text(encoding="utf-8")
            state = json.loads(state_text)
            memory = (output_dir / "_learnings.md").read_text(encoding="utf-8")
            self.assertEqual(code, 1)
            self.assertEqual(state["status"], "failed")
            self.assertEqual(state["error"], "pipeline execution failed")
            self.assertNotIn("run=qa-memory-failure status=succeeded", memory)
            self.assertNotIn("private memory detail", state_text + stderr.getvalue())

    def test_succeeded_state_write_failure_prevents_success_learning(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            run_dir = output_dir / "runs" / "qa-state-write-failure"
            real_write_json = rp._write_json
            failed_succeeded_write = False

            def fail_succeeded_write(path, payload):
                nonlocal failed_succeeded_write
                if path.name == "state.json" and payload.get("status") == "succeeded" and not failed_succeeded_write:
                    failed_succeeded_write = True
                    raise OSError("private final-state detail")
                real_write_json(path, payload)

            with mock.patch.object(rp, "_write_json", side_effect=fail_succeeded_write):
                code = rp.run_cli([
                    "--run-id", "qa-state-write-failure",
                    "--input-dir", str(input_dir),
                    "--output-dir", str(output_dir),
                ])

            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            memory = (output_dir / "_learnings.md").read_text(encoding="utf-8")
            self.assertTrue(failed_succeeded_write)
            self.assertEqual(code, 1)
            self.assertEqual(state["status"], "failed")
            self.assertNotIn("run=qa-state-write-failure status=succeeded", memory)

    def test_learning_append_observes_succeeded_state_before_terminal_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            run_dir = output_dir / "runs" / "qa-learning-order"
            statuses_at_append = []

            def fail_append(*_args):
                state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
                statuses_at_append.append(state["status"])
                raise rp.pm.MemoryEntryError("private append detail")

            with mock.patch.object(rp.pm, "append_learning", side_effect=fail_append):
                code = rp.run_cli([
                    "--run-id", "qa-learning-order",
                    "--input-dir", str(input_dir),
                    "--output-dir", str(output_dir),
                ])

            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            memory = (output_dir / "_learnings.md").read_text(encoding="utf-8")
            self.assertEqual(statuses_at_append, ["succeeded"])
            self.assertEqual(code, 1)
            self.assertEqual(state["status"], "failed")
            self.assertNotIn("run=qa-learning-order status=succeeded", memory)

    def test_parent_fsync_failure_after_learning_replace_preserves_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_dir = Path(tmp) / "input"
            output_dir = Path(tmp) / "output"
            run_dir = output_dir / "runs" / "qa-committed-learning"
            real_replace = rp.sf.os.replace
            real_fsync = rp.sf.os.fsync
            learning_replacements = 0
            fail_next_fsync = False
            stderr = io.StringIO()

            def track_learning_replace(source, destination, *args, **kwargs):
                nonlocal learning_replacements, fail_next_fsync
                result = real_replace(source, destination, *args, **kwargs)
                if destination == "_learnings.md":
                    learning_replacements += 1
                    fail_next_fsync = learning_replacements == 2
                return result

            def fail_committed_parent_fsync(descriptor):
                nonlocal fail_next_fsync
                if fail_next_fsync:
                    fail_next_fsync = False
                    raise OSError("private parent durability detail")
                return real_fsync(descriptor)

            with mock.patch.object(rp.sf.os, "replace", side_effect=track_learning_replace):
                with mock.patch.object(rp.sf.os, "fsync", side_effect=fail_committed_parent_fsync):
                    with contextlib.redirect_stderr(stderr):
                        code = rp.run_cli([
                            "--run-id", "qa-committed-learning",
                            "--input-dir", str(input_dir),
                            "--output-dir", str(output_dir),
                        ])

            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            memory = (output_dir / "_learnings.md").read_text(encoding="utf-8")
            success = "run=qa-committed-learning status=succeeded"
            self.assertEqual(learning_replacements, 2)
            self.assertEqual(
                (code, state["status"], memory.count(success)),
                (0, "succeeded", 1),
            )
            self.assertEqual(
                stderr.getvalue(),
                "pipeline succeeded; learning durability could not be confirmed\n",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
