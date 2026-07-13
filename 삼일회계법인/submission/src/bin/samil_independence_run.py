#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Final

from independence_screen import (
    CliArgs,
    CsvRowFormatError,
    InputFormatError,
    RuleFormatError,
    load_audit_clients,
    load_non_audit_services,
    load_rules,
    parse_cli_args,
    screen,
)
from samil_independence.reporting import render_markdown, risk_counts
from samil_independence.runtime import (
    CONTEXT_BUDGET_TEXT,
    MAX_CONTEXT_BYTES,
    MAX_CONTEXT_LINES,
    SAFE_RUN_ID,
    InvalidRunIdError,
    append_learning,
    prepare_run_paths,
    render_review,
    render_spec,
    render_state,
    review_report,
    select_memory_context,
    write_text,
)

HELP_TEXT: Final = (
    "Usage: python3 src/bin/samil_independence_run.py --audit-clients PATH "
    "--non-audit-services PATH --rules PATH [--run-id ID] "
    "[--input-dir PATH] [--output-dir PATH] [--memory-dir PATH]\n"
)
DEFAULT_INPUT_DIR: Final = Path("input")
DEFAULT_OUTPUT_DIR: Final = Path("output")
DEFAULT_MEMORY_DIR: Final = Path("state") / "memory"


def parse_run_args(argv: tuple[str, ...]) -> tuple[CliArgs, str, Path, Path, Path]:
    wrapper_values: dict[str, str] = {}
    core_args: list[str] = []
    index = 0
    while index < len(argv):
        flag = argv[index]
        if flag in ("--run-id", "--input-dir", "--output-dir", "--memory-dir"):
            next_index = index + 1
            if next_index >= len(argv):
                raise SystemExit(f"missing value for {flag}")
            if flag in wrapper_values:
                raise SystemExit(f"duplicate option: {flag}")
            wrapper_values[flag] = argv[next_index]
            index += 2
            continue
        core_args.append(flag)
        if index + 1 < len(argv) and not argv[index + 1].startswith("--"):
            core_args.append(argv[index + 1])
            index += 2
            continue
        index += 1
    cli_args = parse_cli_args(tuple(core_args))
    run_id = wrapper_values.get("--run-id", "latest")
    input_dir = Path(wrapper_values.get("--input-dir", DEFAULT_INPUT_DIR))
    output_dir = Path(wrapper_values.get("--output-dir", DEFAULT_OUTPUT_DIR))
    memory_dir = Path(wrapper_values.get("--memory-dir", DEFAULT_MEMORY_DIR))
    return cli_args, run_id, input_dir, output_dir, memory_dir


def main() -> int:
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(HELP_TEXT)
        return 0

    args, run_id, input_dir, output_dir, memory_dir = parse_run_args(tuple(sys.argv[1:]))
    if SAFE_RUN_ID.fullmatch(run_id) is None:
        print(str(InvalidRunIdError(run_id=run_id)), file=sys.stderr)
        return 1
    if (input_dir / run_id).exists() or (output_dir / run_id).exists():
        print(f"run already exists: {run_id}", file=sys.stderr)
        return 1
    try:
        paths = prepare_run_paths(
            input_dir=input_dir,
            output_dir=output_dir,
            memory_dir=memory_dir,
            run_id=run_id,
        )
    except InvalidRunIdError as error:
        print(str(error), file=sys.stderr)
        return 1
    write_text(
        paths.input_run_dir / "spec.md",
        render_spec(run_id, args.audit_clients, args.non_audit_services, args.rules),
    )
    snapshot_supplied_inputs(paths.input_run_dir, args)
    try:
        audit_clients = load_audit_clients(args.audit_clients)
        services = load_non_audit_services(args.non_audit_services)
        rules = load_rules(args.rules)
    except (
        CsvRowFormatError,
        InputFormatError,
        RuleFormatError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        write_text(
            paths.input_run_dir / "state.md",
            render_state(
                run_id,
                "failed",
                args.audit_clients,
                args.non_audit_services,
                args.rules,
                (str(error),),
            ),
        )
        write_text(paths.output_run_dir / "error.md", f"{error}\n")
        print(str(error), file=sys.stderr)
        return 2

    rule_labels = tuple(
        sorted((*rules.prohibited_service_types, *rules.review_service_types))
    )
    context = select_memory_context(
        paths.memory_root,
        rule_labels,
        max_lines=MAX_CONTEXT_LINES,
        max_bytes=MAX_CONTEXT_BYTES,
    )
    write_text(
        paths.input_run_dir / "context.md",
        render_context(run_id=run_id, selected_memory=context),
    )
    findings = screen(audit_clients=audit_clients, services=services, rules=rules)
    report = render_markdown(findings)
    review = review_report(report)
    write_text(paths.output_run_dir / "report.md", report)
    write_text(paths.output_run_dir / "review.md", render_review(run_id, review))
    write_text(
        paths.input_run_dir / "state.md",
        render_state(
            run_id,
            "review_passed" if review.passed else "review_failed",
            args.audit_clients,
            args.non_audit_services,
            args.rules,
            (f"selected_memory_lines={len(context.splitlines())}",),
        ),
    )
    if review.passed:
        append_learning(
            memory_root=paths.memory_root,
            run_id=run_id,
            status="review_passed",
            rule_labels=rule_labels,
            counts=risk_counts(findings),
            process_lesson="Use supplied rule labels and preserve triage limitations.",
            redacted_sample=report,
        )
    print(report)
    return 0 if review.passed else 3


def snapshot_supplied_inputs(input_run_dir: Path, args: CliArgs) -> None:
    snapshots = (
        (args.audit_clients, "audit_clients.csv"),
        (args.non_audit_services, "non_audit_services.csv"),
        (args.rules, "independence_rules.json"),
    )
    for source, name in snapshots:
        if not source.is_file():
            continue
        shutil.copyfile(source, input_run_dir / name)


def render_context(run_id: str, selected_memory: str) -> str:
    memory = selected_memory if selected_memory else "- no selected prior learning"
    return "\n".join(
        [
            "# Context Pack",
            "",
            f"- run_id: {run_id}",
            "- source: redacted append-only local memory",
            f"- budget: {CONTEXT_BUDGET_TEXT}",
            "",
            "## Selected Memory",
            "",
            memory,
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
