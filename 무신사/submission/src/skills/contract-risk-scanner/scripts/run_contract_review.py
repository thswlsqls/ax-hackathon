#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, TextIO

# scan_contract is imported as a module; opt out of bytecode caching before the
# import so no scripts/__pycache__/ is written under submission/src (the
# regression gate in test_pipeline_edges.py asserts none exists).
sys.dont_write_bytecode = True

from render_review_artifacts import (
    ArtifactPaths,
    Baseline,
    RunRequest,
    SafeBaseline,
    SafeFinding,
    SourceKind,
    artifact_name,
    render_baseline,
    render_input,
    render_report,
    render_review,
    render_state,
    sanitize_baseline,
)
from render_review_artifacts import cell, report_row, review_row
from scan_contract import load_rules, scan


__all__ = ["SafeFinding", "cell", "report_row", "review_row"]

SKILL_DIR: Final = Path(__file__).resolve().parents[1]
CONFIG_PATH: Final = SKILL_DIR / "config" / "musinsa-config.json"
RUN_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def write_owned_text(directory_fd: int, name: str, text: str) -> None:
    payload = text.encode("utf-8")
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o666,
        dir_fd=directory_fd,
    )
    try:
        bytes_written = 0
        while bytes_written < len(payload):
            write_count = os.write(descriptor, payload[bytes_written:])
            if write_count == 0:
                raise OSError("artifact write made no progress")
            bytes_written += write_count
    finally:
        os.close(descriptor)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a local contract-risk review run"
    )
    parser.add_argument("--input", type=Path, help="Local contract text file")
    parser.add_argument(
        "--input-dir", type=Path, default=SKILL_DIR.parents[2] / "input"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=SKILL_DIR.parents[2] / "output"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--privacy-mode", default="local_only")
    parser.add_argument("--demo", action="store_true", help="Use the synthetic fixture")
    return parser.parse_args()


def build_request(args: argparse.Namespace) -> RunRequest:
    if not RUN_ID_PATTERN.fullmatch(args.run_id):
        raise UsageError(
            "run id must use only letters, numbers, dot, underscore, or hyphen"
        )
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if args.privacy_mode != str(config["privacy"]["mode"]):
        raise UsageError(f"unsupported privacy mode: {args.privacy_mode}")
    if args.demo:
        input_path = SKILL_DIR / "fixtures" / "sample_contract_01.md"
        source_kind: SourceKind = "demo_fixture"
    elif args.input is not None:
        input_path = args.input
        source_kind = "local_file"
    else:
        raise UsageError("provide --demo or --input")
    if not input_path.exists():
        raise MissingInputError(input_path)
    return RunRequest(
        input_path.resolve(),
        args.input_dir.absolute(),
        args.output_dir.absolute(),
        args.run_id,
        args.privacy_mode,
        source_kind,
        str(config["report_policy"]["disclaimer"]),
    )


def write_run(request: RunRequest) -> ArtifactPaths:
    for existing_run_dir in (
        run_dir
        for run_dir in (
            request.input_dir / request.run_id,
            request.output_dir / request.run_id,
        )
        if run_dir.exists()
    ):
        raise UsageError(f"run already exists: {existing_run_dir}")
    paths = ArtifactPaths(
        request.input_dir / artifact_name(request.run_id, "input.md"),
        *(
            request.output_dir / artifact_name(request.run_id, name)
            for name in ("baseline.json", "review.md", "report.md", "state.md")
        ),
    )
    for existing_target in (target for target in paths if target.exists()):
        raise UsageError(f"run already exists: {existing_target}")
    root_directory_fds: list[int] = []
    learning_handle: TextIO | None = None
    try:
        for root_directory in (request.input_dir, request.output_dir):
            root_directory_fds.append(
                os.open(
                    root_directory,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                )
            )
        learning_handle = reserve_learning_memory(root_directory_fds[1])
        _meta, rules = load_rules(str(SKILL_DIR / "rules" / "clause_rules.json"))
        findings = scan(request.input_path.read_text(encoding="utf-8"), rules)
        baseline: Baseline = {
            "source": str(request.input_path),
            "count": len(findings),
            "findings": findings,
        }
        safe_baseline = sanitize_baseline(baseline)
        write_input(request, root_directory_fds[0])
        write_owned_text(
            root_directory_fds[1],
            artifact_name(request.run_id, "baseline.json"),
            render_baseline(baseline),
        )
        write_review(safe_baseline, root_directory_fds[1], request.run_id)
        write_report(request, safe_baseline, root_directory_fds[1])
        write_state(paths, request, root_directory_fds[1])
        append_learning(
            request,
            len(findings),
            learning_handle,
            root_directory_fds[1],
        )
    finally:
        if learning_handle is not None:
            learning_handle.close()
        for root_directory_fd in root_directory_fds:
            os.close(root_directory_fd)
    return paths


def write_input(request: RunRequest, directory_fd: int) -> None:
    write_owned_text(
        directory_fd,
        artifact_name(request.run_id, "input.md"),
        render_input(request),
    )


def write_review(baseline: SafeBaseline, directory_fd: int, run_id: str) -> None:
    write_owned_text(
        directory_fd,
        artifact_name(run_id, "review.md"),
        render_review(baseline, run_id),
    )


def write_report(
    request: RunRequest,
    baseline: SafeBaseline,
    directory_fd: int,
) -> None:
    write_owned_text(
        directory_fd,
        artifact_name(request.run_id, "report.md"),
        render_report(request, baseline),
    )


def write_state(paths: ArtifactPaths, request: RunRequest, directory_fd: int) -> None:
    write_owned_text(
        directory_fd,
        artifact_name(request.run_id, "state.md"),
        render_state(paths, request),
    )


def reserve_learning_memory(output_directory_fd: int) -> TextIO | None:
    try:
        descriptor = os.open(
            "_learnings.md",
            os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW,
            dir_fd=output_directory_fd,
        )
    except FileNotFoundError:
        return None
    try:
        identity = os.fstat(descriptor)
    except OSError:
        os.close(descriptor)
        raise
    if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1:
        os.close(descriptor)
        raise OSError("learning memory must be a singly linked regular file")
    try:
        return os.fdopen(descriptor, "a", encoding="utf-8")
    except (OSError, ValueError):
        os.close(descriptor)
        raise


def append_learning(
    request: RunRequest,
    finding_count: int,
    learning_handle: TextIO | None,
    output_directory_fd: int,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    line = f"| {request.run_id} | {now} | {request.source_kind} | {finding_count} | local pipeline run appended after reread |\n"
    if learning_handle is not None:
        learning_handle.write(line)
    else:
        template = SKILL_DIR / "templates" / "learnings_TEMPLATE.md"
        descriptor = os.open(
            "_learnings.md",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o666,
            dir_fd=output_directory_fd,
        )
        try:
            handle = os.fdopen(descriptor, "w", encoding="utf-8")
        except (OSError, ValueError):
            os.close(descriptor)
            raise
        with handle:
            handle.write(template.read_text(encoding="utf-8"))
            handle.write(line)


class UsageError(Exception):
    """User supplied an invalid run request."""


class MissingInputError(Exception):
    """The requested input file does not exist."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"계약서 파일을 찾을 수 없습니다: {path}")


def main() -> int:
    try:
        request = build_request(parse_args())
        paths = write_run(request)
    except (MissingInputError, UsageError) as error:
        print(error)
        return 2
    except UnicodeError:
        print(
            "계약서 파일을 UTF-8 텍스트로 읽을 수 없습니다: PDF·바이너리는 미지원이니 텍스트로 추출해 전달하세요."
        )
        return 2
    print(f"input record: {paths.input_record}")
    print(f"output artifacts: {request.output_dir}")
    print("output files: " + " ".join(str(path.name) for path in paths[1:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
