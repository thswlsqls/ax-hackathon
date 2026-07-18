#!/usr/bin/env python3
from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SUBMISSION_ROOT = SKILL_ROOT.parents[2]
CORE_TEST_FILES = (
    "test_analyze_incidents.py",
    "test_chaos_scenarios.py",
    "test_pipeline_memory.py",
    "test_resilience.py",
    "test_run_pipeline.py",
)
CORE_TEST_BASELINE = 70
# NOTE: `input`/`output` are intentionally NOT treated as generated artifacts.
# Curated, sanitized sample runs are published under these directories to stay
# consistent with the sibling submissions (무신사/삼일회계법인), which ship their
# example runs the same way. Uncurated runtime scratch (test-runs, manual, caches)
# is still kept out of the packaged tree via .gitignore.
GENERATED_DIRECTORY_NAMES = {
    ".codebase-memory",
    ".mypy_cache",
    ".omo",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}
GENERATED_FILE_NAMES = {".DS_Store", "chaos-report.json", "stability-report.json"}
GENERATED_SUFFIXES = {".pyc", ".pyo"}
PUBLIC_LOG_DIRECTORY = Path("logs")
ALLOWED_PUBLIC_LOG = PUBLIC_LOG_DIRECTORY / "submission-evidence.jsonl"
ALLOWED_PUBLIC_LOG_CONTENT = (
    b'{"type":"submission_evidence","source":"sanitized","status":"retained"}\n'
)
ALLOWED_IMPORTS = {
    "__future__",
    "argparse",
    "ast",
    "collections",
    "concurrent",
    "contextlib",
    "datetime",
    "fcntl",
    "importlib",
    "io",
    "json",
    "os",
    "pathlib",
    "re",
    "secrets",
    "shutil",
    "signal",
    "stat",
    "sys",
    "tempfile",
    "threading",
    "time",
    "traceback",
    "types",
    "unicodedata",
    "unittest",
    "typing",
}
LOCAL_IMPORTS = {
    "analyze_incidents",
    "broker_mock",
    "demo",
    "io_contract",
    "incident_schema",
    "pipeline_memory",
    "pipeline_contracts",
    "resilience",
    "run_pipeline",
    "safe_filesystem",
    "scripts",
    "trading_backend",
}


def generated_artifacts(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if is_generated_artifact(path, root)
    )


def is_generated_artifact(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if relative == PUBLIC_LOG_DIRECTORY:
        return path.is_symlink() or not path.is_dir()
    if relative == ALLOWED_PUBLIC_LOG:
        if path.is_symlink() or not path.is_file():
            return True
        try:
            return path.read_bytes() != ALLOWED_PUBLIC_LOG_CONTENT
        except OSError:
            return True
    if relative.parts[:1] == (str(PUBLIC_LOG_DIRECTORY),):
        return True
    return (
        path.name in GENERATED_DIRECTORY_NAMES
        or path.name in GENERATED_FILE_NAMES
        or path.suffix in GENERATED_SUFFIXES
    )


def count_test_methods(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(tree)
    )


DISCOVERY_GENERATED_ARTIFACTS = tuple(generated_artifacts(SUBMISSION_ROOT))


class PackagingCleanlinessTest(unittest.TestCase):
    def test_core_test_baseline_is_70(self) -> None:
        tests_root = SKILL_ROOT / "tests"
        actual = sum(count_test_methods(tests_root / name) for name in CORE_TEST_FILES)
        self.assertEqual(actual, CORE_TEST_BASELINE)

    def test_generated_artifact_detector_finds_controlled_run_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            # A generated run report is detected by name even under a retained
            # output/ tree (input/output themselves are no longer forbidden).
            report = root / "output" / "runs" / "controlled" / "chaos-report.json"
            report.parent.mkdir(parents=True)
            _ = report.write_text("{}\n", encoding="utf-8")

            self.assertIn(report, generated_artifacts(root))

            logs = root / "logs"
            external_logs = root / "external-logs"
            external_logs.mkdir()
            logs.symlink_to(external_logs, target_is_directory=True)
            self.assertIn(logs, generated_artifacts(root))

            logs.unlink()
            logs.mkdir()
            raw_log = logs / "raw-transcript.txt"
            _ = raw_log.write_text("private\n", encoding="utf-8")
            self.assertIn(raw_log, generated_artifacts(root))

            raw_log.unlink()
            public_log = root / ALLOWED_PUBLIC_LOG
            public_log.symlink_to(external_logs / "marker.jsonl")
            self.assertIn(public_log, generated_artifacts(root))

            public_log.unlink()
            _ = public_log.write_text("RAW TOKEN=secret\n", encoding="utf-8")
            self.assertIn(public_log, generated_artifacts(root))

            _ = public_log.write_bytes(ALLOWED_PUBLIC_LOG_CONTENT)
            self.assertNotIn(public_log, generated_artifacts(root))

    def test_submission_tree_has_no_generated_artifacts(self) -> None:
        self.assertEqual(DISCOVERY_GENERATED_ARTIFACTS, ())

    def test_no_requirements_file_or_third_party_imports_added(self) -> None:
        self.assertFalse((SKILL_ROOT / "requirements.txt").exists())
        unexpected: list[tuple[str, str]] = []
        for path in SKILL_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    unexpected.extend(
                        (str(path), alias.name.split(".")[0])
                        for alias in node.names
                        if alias.name.split(".")[0] not in ALLOWED_IMPORTS | LOCAL_IMPORTS
                    )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    name = node.module.split(".")[0]
                    if name not in ALLOWED_IMPORTS | LOCAL_IMPORTS:
                        unexpected.append((str(path), name))
        self.assertEqual(unexpected, [])

    def test_templates_and_docs_do_not_keep_placeholders(self) -> None:
        checked_roots = (SUBMISSION_ROOT / "README.md", SUBMISSION_ROOT / "docs")
        offenders: list[str] = []
        for root in checked_roots:
            paths = [root] if root.is_file() else list(root.rglob("*.md"))
            for path in paths:
                text = path.read_text(encoding="utf-8")
                if any(token in text for token in ("TODO", "TBD", "<pattern>", "{slug}")):
                    offenders.append(str(path.relative_to(SUBMISSION_ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    _ = unittest.main(verbosity=2)
