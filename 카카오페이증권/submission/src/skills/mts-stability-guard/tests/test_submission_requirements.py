#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Final
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

# isort: split
import io_contract
from io_contract import (
    SubmissionIOTestCase,
    safe_test_id,
)

SKILL_ROOT = Path(__file__).resolve().parents[1]
SUBMISSION_ROOT = SKILL_ROOT.parents[2]
EXPECTED_LOG_PATH: Final = Path("logs/submission-evidence.jsonl")
EXPECTED_LOG_BYTES: Final = (
    b'{"type":"submission_evidence","source":"sanitized","status":"retained"}\n'
)
EXPECTED_LOG_OBJECT: Final = {
    "type": "submission_evidence",
    "source": "sanitized",
    "status": "retained",
}


def _read_text(relative_path: str) -> str:
    return (SUBMISSION_ROOT / relative_path).read_text(encoding="utf-8")


def _test_method_count() -> int:
    count = 0
    for path in (SKILL_ROOT / "tests").glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        count += sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
            for node in ast.walk(tree)
        )
    return count


class SubmissionRequirementTest(SubmissionIOTestCase):
    def test_plugin_root_contains_manifest_and_skill_component(self) -> None:
        manifest = SUBMISSION_ROOT / "src" / ".codex-plugin" / "plugin.json"
        skill = SUBMISSION_ROOT / "src" / "skills" / "mts-stability-guard" / "SKILL.md"

        parsed = json.loads(manifest.read_text(encoding="utf-8"))

        self.assertEqual(parsed["name"], "mts-stability-guard")
        self.assertEqual(parsed["skills"], "./skills/")
        self.assertTrue(skill.exists())

    def test_logs_contain_only_exact_sanitized_submission_marker(self) -> None:
        logs_root = SUBMISSION_ROOT / "logs"
        marker = SUBMISSION_ROOT / EXPECTED_LOG_PATH
        entries = sorted(
            path.relative_to(SUBMISSION_ROOT) for path in logs_root.rglob("*")
        )

        self.assertTrue(logs_root.is_dir())
        self.assertFalse(logs_root.is_symlink())
        self.assertEqual(entries, [EXPECTED_LOG_PATH])
        self.assertTrue(marker.is_file())
        self.assertFalse(marker.is_symlink())
        self.assertEqual(marker.read_bytes(), EXPECTED_LOG_BYTES)
        self.assertEqual(
            json.loads(marker.read_text(encoding="utf-8")),
            EXPECTED_LOG_OBJECT,
        )

    def test_incident_sample_exposes_machine_checkable_public_urls(self) -> None:
        data = json.loads(
            (SKILL_ROOT / "data" / "incidents.sample.json").read_text(
                encoding="utf-8",
            ),
        )

        self.assertGreaterEqual(len(data["meta"]["source_urls"]), 3)
        self.assertTrue(data["annual_counts"]["source_url"].startswith("https://"))
        for incident in data["incidents"]:
            self.assertTrue(
                incident["source_url"].startswith("https://"),
                msg=incident["id"],
            )

    def test_questionnaire_and_readme_verification_counts_match_tests(self) -> None:
        actual = _test_method_count()
        expected = f"{actual}개"
        combined = "\n".join([
            _read_text("README.md"),
            _read_text("docs/예선-질문-5문항.md"),
        ])

        self.assertEqual(actual, 81)
        self.assertIn(expected, combined)
        self.assertNotIn("27개", combined)

    def test_questionnaire_answers_stay_within_declared_length_bound(self) -> None:
        text = _read_text("docs/예선-질문-5문항.md")

        for number in range(1, 6):
            match = re.search(
                rf"## {number}\. .*?\n\n(.+?)(?=\n\n## |\n\n> \*\*{number}번|\Z)",
                text,
                re.DOTALL,
            )
            if match is None:
                self.fail(f"question {number}")
            answer = match.group(1).split("\n\n>")[0].strip()
            self.assertGreaterEqual(len(answer), 700, msg=f"question {number}")
            self.assertLessEqual(len(answer), 800, msg=f"question {number}")

    def test_submission_io_pair_exists_for_this_test_execution(self) -> None:
        class ProbeCase(SubmissionIOTestCase):
            def probe(self) -> None:
                return None

        probe = ProbeCase("probe")
        result = unittest.TestResult()
        safe_id = safe_test_id(probe.id())
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            probe_input_root = temporary_root / "input"
            probe_output_root = temporary_root / "output"
            with (
                mock.patch.object(io_contract, "TEST_INPUT_ROOT", probe_input_root),
                mock.patch.object(io_contract, "TEST_OUTPUT_ROOT", probe_output_root),
            ):
                returned = probe.run(result)

            input_artifact = probe_input_root / safe_id / "input.json"
            output_artifact = probe_output_root / safe_id / "output.json"
            self.assertIs(returned, result)
            self.assertTrue(result.wasSuccessful())
            self.assertTrue(input_artifact.is_file())
            self.assertTrue(output_artifact.is_file())
            input_record = json.loads(input_artifact.read_text(encoding="utf-8"))
            output_record = json.loads(output_artifact.read_text(encoding="utf-8"))
            self.assertEqual(input_record["test_id"], probe.id())
            self.assertEqual(output_record["test_id"], probe.id())
            self.assertEqual(input_record["execution_unit"], safe_id)
            self.assertEqual(output_record["execution_unit"], safe_id)
            self.assertEqual(output_record["status"], "passed")


if __name__ == "__main__":
    _ = unittest.main(verbosity=2)
