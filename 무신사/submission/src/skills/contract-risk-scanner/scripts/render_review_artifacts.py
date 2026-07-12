from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, NamedTuple, TypedDict

from scan_contract import Finding


SourceKind = Literal["demo_fixture", "local_file"]


class Baseline(TypedDict):
    source: str
    count: int
    findings: list[Finding]


class SafeFinding(TypedDict):
    clause: str
    rule_id: str
    rule_name: str
    risk: str
    matched_terms: list[str]
    law_reference: str
    suggestion: str


class SafeBaseline(TypedDict):
    source: str
    count: int
    findings: list[SafeFinding]


class RunRequest(NamedTuple):
    input_path: Path
    input_dir: Path
    output_dir: Path
    run_id: str
    privacy_mode: str
    source_kind: SourceKind
    report_disclaimer: str


class ArtifactPaths(NamedTuple):
    input_record: Path
    baseline: Path
    review: Path
    report: Path
    state: Path


def artifact_name(run_id: str, name: str) -> str:
    return f"{run_id}--{name}"


def sanitize_baseline(baseline: Baseline) -> SafeBaseline:
    return {
        "source": baseline["source"],
        "count": baseline["count"],
        "findings": [
            {
                "clause": finding["clause"],
                "rule_id": finding["rule_id"],
                "rule_name": finding["rule_name"],
                "risk": finding["risk"],
                "matched_terms": finding["matched_terms"],
                "law_reference": finding["law_reference"],
                "suggestion": finding["suggestion"],
            }
            for finding in baseline["findings"]
        ],
    }


def render_input(request: RunRequest) -> str:
    return "\n".join(
        [
            "# Input Record",
            "",
            f"- run_id: `{request.run_id}`",
            f"- source_kind: `{request.source_kind}`",
            f"- source_path: `{request.input_path}`",
            f"- privacy_mode: `{request.privacy_mode}`",
            "- redaction_summary: raw local file text was not copied into role prompts",
            f"- scanner_input: `{request.input_path}`",
            f"- output_artifact_set: `{request.output_dir / artifact_name(request.run_id, '{baseline.json,review.md,report.md,state.md}')}`",
            "",
        ]
    )


def render_baseline(baseline: Baseline) -> str:
    return json.dumps(baseline, ensure_ascii=False, indent=2) + "\n"


def render_review(baseline: SafeBaseline, run_id: str) -> str:
    lines = [
        "# Review Draft",
        "",
        "> 본 초안은 법률 자문이 아니다. 결정론적 baseline 후보를 문맥 검토 큐로 정리한 것이다.",
        "",
        f"- baseline_path: `{artifact_name(run_id, 'baseline.json')}`",
        "- learning_context: `none`",
        "",
        "## Decisions",
        "| rule_id | clause | baseline_risk | confidence | decision | reason | rewrite_candidate |",
        "|---|---|---|---|---|---|---|",
    ]
    if not baseline["findings"]:
        lines.append(
            "| - | - | - | 낮음 | needs-human-review | 규칙 매칭 없음 | 수동 검토 |"
        )
    else:
        lines.extend(review_row(finding) for finding in baseline["findings"])
    return "\n".join(lines) + "\n"


def render_report(request: RunRequest, baseline: SafeBaseline) -> str:
    lines = [
        "# 계약서 리스크 점검 리포트",
        "",
        f"> {request.report_disclaimer}",
        "",
        "## Summary",
        f"- target: `{request.input_path}`",
        f"- finding_count: {baseline['count']}",
        "",
        "## Findings",
        "| priority | risk | clause | issue | legal_basis_candidate | suggested_rewrite | confidence |",
        "|---:|---|---|---|---|---|---|",
    ]
    if baseline["findings"]:
        lines.extend(
            report_row(index, finding)
            for index, finding in enumerate(baseline["findings"], 1)
        )
    else:
        lines.append(
            "| 1 | 하 | - | 규칙 매칭 없음 | - | 중요 계약은 수동 검토 | 낮음 |"
        )
    lines.extend(
        [
            "",
            "## Human Review Queue",
            "- 상 등급 후보와 비용전가·경쟁제한 후보를 먼저 검토한다.",
            "",
        ]
    )
    return "\n".join(lines)


def render_state(paths: ArtifactPaths, request: RunRequest) -> str:
    lines = [
        "# Run State",
        "",
        "## Status",
        f"- run_id: `{request.run_id}`",
        "- current_status: `reported`",
        f"- input_path: `{paths.input_record}`",
        f"- baseline_path: `{artifact_name(request.run_id, 'baseline.json')}`",
        f"- review_path: `{artifact_name(request.run_id, 'review.md')}`",
        f"- report_path: `{artifact_name(request.run_id, 'report.md')}`",
        "- validation_result: `pending`",
        "",
        "## Append-Only History",
        "| status | artifact | note |",
        "|---|---|---|",
        f"| created | {paths.input_record} | input normalized |",
        f"| scanned | {artifact_name(request.run_id, 'baseline.json')} | scanner baseline created |",
        f"| reviewed | {artifact_name(request.run_id, 'review.md')} | role review draft created |",
        f"| reported | {artifact_name(request.run_id, 'report.md')} | report draft created |",
        "",
    ]
    return "\n".join(lines)


def cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def review_row(finding: SafeFinding) -> str:
    return "| {rule_id} | {clause} | {risk} | 중간 | keep | baseline rule matched; human review required | {suggestion} |".format(
        rule_id=cell(finding["rule_id"]),
        clause=cell(finding["clause"]),
        risk=cell(finding["risk"]),
        suggestion=cell(finding["suggestion"]),
    )


def report_row(index: int, finding: SafeFinding) -> str:
    return "| {index} | {risk} | {clause} | {issue} | {law} | {suggestion} | 중간 |".format(
        index=index,
        risk=cell(finding["risk"]),
        clause=cell(finding["clause"]),
        issue=cell(finding["rule_name"]),
        law=cell(finding["law_reference"]),
        suggestion=cell(finding["suggestion"]),
    )
