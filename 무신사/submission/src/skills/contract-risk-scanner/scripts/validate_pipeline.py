#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Validate the local contract-risk review pipeline."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Final, NamedTuple, TypedDict


DISCLAIMER: Final = "법률 자문이 아니다"
FORBIDDEN_LEGAL_WORDS: Final = ("위법 확정", "불법", "법적으로 위반", "illegal")
REQUIRED_LEARNING_SECTIONS: Final = (
    "## Run Tracking",
    "## False-Positive Registry",
    "## Rule Gaps",
    "## Rewrite Candidates",
    "## Process Lessons",
)
REQUIRED_ROLE_GUARDS: Final = ("법률 자문이 아니다", "local_only", "do not use network")
REQUIRED_STATE_STATUSES: Final = ("created", "scanned", "reviewed", "reported")
NETWORK_TOKENS: Final = ("curl", "requests", "urllib", "http://", "https://", "gh ", "sqlite", "chromadb", "faiss", "pinecone")


class Baseline(TypedDict):
    source: str
    count: int
    findings: list["BaselineFinding"]


class BaselineFinding(TypedDict):
    rule_id: str
    snippet: str


class ValidationTarget(NamedTuple):
    skill_dir: Path
    input_dir: Path
    output_dir: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the contract-risk review pipeline")
    parser.add_argument("--skill-dir", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--negative-sample",
        choices=["missing-disclaimer", "forbidden-network", "bad-baseline"],
    )
    return parser.parse_args()


def run_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=False, text=True, capture_output=True)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_all(target: ValidationTarget) -> None:
    validate_config(target.skill_dir)
    validate_templates(target.skill_dir)
    validate_roles(target.skill_dir)
    validate_scanner_baseline(target.skill_dir)
    paths = ensure_demo_run(target)
    validate_artifacts(paths, target.output_dir)
    validate_source_policy(target.skill_dir)


def validate_config(skill_dir: Path) -> None:
    config = json.loads((skill_dir / "config" / "musinsa-config.json").read_text(encoding="utf-8"))
    for key in ("paths", "privacy", "scanner", "artifacts", "memory", "report_policy", "validation", "role_inputs"):
        assert_true(key in config, f"missing config key: {key}")
    assert_true(config["privacy"]["mode"] == "local_only", "privacy.mode must be local_only")
    allowed = config["privacy"]["allowed_model_context"]
    assert_true(allowed == ["synthetic_fixtures", "explicit_user_paste"], "unexpected allowed_model_context")
    tokens = set(config["validation"]["forbidden_network_tokens"])
    for token in NETWORK_TOKENS:
        assert_true(token in tokens, f"missing forbidden token: {token}")
    artifacts = config["artifacts"]
    for key in ("input", "baseline", "review", "report", "state"):
        assert_true("<run-id>--" in artifacts[key], f"artifact {key} is not flat")


def validate_templates(skill_dir: Path) -> None:
    templates = skill_dir / "templates"
    required = {
        "input_TEMPLATE.md": ("run_id", "privacy_mode", "scanner_input"),
        "review_TEMPLATE.md": ("baseline_path", "decisions", "rewrite_candidate"),
        "report_TEMPLATE.md": (DISCLAIMER, "Human Review Queue", "suggested_rewrite"),
        "state_TEMPLATE.md": ("run_id", "validation_result", "created", "scanned", "reviewed", "reported"),
        "learnings_TEMPLATE.md": REQUIRED_LEARNING_SECTIONS,
    }
    for name, needles in required.items():
        text = (templates / name).read_text(encoding="utf-8")
        for needle in needles:
            assert_true(needle in text, f"{name} missing {needle}")


def validate_roles(skill_dir: Path) -> None:
    for path in sorted((skill_dir / "roles").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert_true("<run-id>--" in text, f"{path.name} missing flat artifact contract")
        for guard in REQUIRED_ROLE_GUARDS:
            assert_true(guard in text, f"{path.name} missing {guard}")
        for heading in ("## Allowed Inputs", "## Forbidden Inputs", "## Output Artifact", "## Failure Modes"):
            assert_true(heading in text, f"{path.name} missing {heading}")
    assert_true(len(list((skill_dir / "roles").glob("*.md"))) == 4, "expected four role prompts")


def validate_scanner_baseline(skill_dir: Path) -> None:
    verify = run_command(["python3", str(skill_dir / "scripts" / "verify_fixtures.py")], skill_dir.parents[4])
    assert_true(verify.returncode == 0, verify.stdout + verify.stderr)
    assert_true("fixture verification passed: 13 scenarios" in verify.stdout, "fixture verifier output changed")
    scan = run_command(
        [
            "python3",
            str(skill_dir / "scripts" / "scan_contract.py"),
            str(skill_dir / "fixtures" / "sample_contract_01.md"),
            "--format",
            "json",
            "--min-risk",
            "상",
        ],
        skill_dir.parents[4],
    )
    assert_true(scan.returncode == 0, scan.stdout + scan.stderr)
    baseline = json.loads(scan.stdout)
    ids = [finding["rule_id"] for finding in baseline["findings"]]
    assert_true(baseline["count"] == 3, "high-risk count changed")
    assert_true(ids == ["R01_multihoming", "R02_mfn", "R03_promo_cost"], "high-risk ids changed")
    missing = run_command(
        ["python3", str(skill_dir / "scripts" / "scan_contract.py"), str(skill_dir / "fixtures" / "missing.md")],
        skill_dir.parents[4],
    )
    assert_true(missing.returncode == 2, "missing input exit changed")
    assert_true("계약서 파일을 찾을 수 없습니다" in missing.stderr, "missing input message changed")


def ensure_demo_run(target: ValidationTarget) -> ArtifactPaths:
    run_id = f"qa-validate-{secrets.token_hex(8)}"
    target.input_dir.mkdir(parents=True, exist_ok=True)
    target.output_dir.mkdir(parents=True, exist_ok=True)
    run = run_command(
        [
            "python3",
            str(target.skill_dir / "scripts" / "run_contract_review.py"),
            "--demo",
            "--run-id",
            run_id,
            "--input-dir",
            str(target.input_dir),
            "--output-dir",
            str(target.output_dir),
        ],
        target.skill_dir.parents[4],
    )
    assert_true(run.returncode == 0, run.stdout + run.stderr)
    return ArtifactPaths(
        target.input_dir / f"{run_id}--input.md",
        *(
            target.output_dir / f"{run_id}--{name}"
            for name in ("baseline.json", "review.md", "report.md", "state.md")
        ),
    )


class ArtifactPaths(NamedTuple):
    input_record: Path
    baseline: Path
    review: Path
    report: Path
    state: Path


def validate_artifacts(paths: ArtifactPaths, output_dir: Path) -> None:
    run_id = paths.baseline.name.removesuffix("--baseline.json")
    assert_true(paths.input_record.exists(), "missing input record: input.md")
    assert_true(not (output_dir / f"{run_id}--input.md").exists(), "output run contains input.md")
    for path in paths[1:]:
        assert_true(path.exists(), f"missing artifact: {path.name}")
    baseline = json.loads(paths.baseline.read_text(encoding="utf-8"))
    for key in ("source", "count", "findings"):
        assert_true(key in baseline, f"baseline missing {key}")
    report = paths.report.read_text(encoding="utf-8")
    assert_report_policy(report)
    review = paths.review.read_text(encoding="utf-8")
    validate_role_artifact_context(review, report, baseline)
    state = paths.state.read_text(encoding="utf-8")
    assert_true(str(paths.input_record) in state, "state missing paired input path")
    for status in REQUIRED_STATE_STATUSES:
        assert_true(status in state, f"state missing status {status}")
    memory = (output_dir / "_learnings.md").read_text(encoding="utf-8")
    for section in REQUIRED_LEARNING_SECTIONS:
        assert_true(section in memory, f"learnings missing {section}")
    assert_true(f"| {run_id} |" in memory, f"learnings missing {run_id} append")


def assert_report_policy(text: str) -> None:
    assert_true(DISCLAIMER in text, "report missing disclaimer")
    for word in FORBIDDEN_LEGAL_WORDS:
        assert_true(word not in text, f"report contains forbidden legal wording: {word}")


def validate_role_artifact_context(review: str, report: str, baseline: Baseline) -> None:
    for finding in baseline["findings"]:
        snippet = finding["snippet"]
        if snippet:
            assert_true(snippet not in review, "review contains raw scanner snippet")
            assert_true(snippet not in report, "report contains raw scanner snippet")


def validate_source_policy(skill_dir: Path) -> None:
    allowed = {
        skill_dir / "config" / "musinsa-config.json",
        skill_dir / "scripts" / "validate_pipeline.py",
    }
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path in allowed or path.suffix not in {".py", ".md", ".json"}:
            continue
        validate_no_token_text(path.read_text(encoding="utf-8"), path)


def validate_negative_sample(kind: str) -> None:
    with tempfile.TemporaryDirectory(prefix="musinsa-validator-") as tmp:
        root = Path(tmp)
        if kind == "missing-disclaimer":
            expect_failure(lambda: assert_report_policy("# report\n검토 결과입니다.\n"))
            return
        if kind == "forbidden-network":
            bad = root / "bad-role.md"
            bad.write_text("do not use network but also requests should be rejected", encoding="utf-8")
            expect_failure(lambda: validate_no_token_text(bad.read_text(encoding="utf-8"), bad))
            return
        bad_json = root / "baseline.json"
        bad_json.write_text(json.dumps({"source": "x"}), encoding="utf-8")
        expect_failure(lambda: validate_baseline_shape(bad_json))


def validate_no_token_text(text: str, path: Path) -> None:
    for token in NETWORK_TOKENS:
        assert_true(not contains_forbidden_token(text, token), f"forbidden token {token!r} in {path}")


def contains_forbidden_token(text: str, token: str) -> bool:
    if token == "gh ":
        return re.search(r"(?<![A-Za-z0-9_-])gh\s", text) is not None
    return token in text


def validate_baseline_shape(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("source", "count", "findings"):
        assert_true(key in data, f"baseline missing {key}")


def expect_failure(callback: Callable[[], None]) -> None:
    try:
        callback()
    except ValidationError:
        return
    raise ValidationError("negative sample unexpectedly passed")


class ValidationError(Exception):
    """Pipeline validation failed."""


def main() -> int:
    args = parse_args()
    try:
        if args.negative_sample is not None:
            validate_negative_sample(args.negative_sample)
            print(f"negative sample rejected: {args.negative_sample}")
            return 0
        validate_all(ValidationTarget(args.skill_dir.resolve(), args.input_dir.resolve(), args.output_dir.resolve()))
    except (ValidationError, json.JSONDecodeError) as error:
        print(f"validation failed: {error}")
        return 1
    print("pipeline validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
