from __future__ import annotations

from typing import Literal, Protocol

RiskLevel = Literal["고위험", "추가 검토 필요", "낮음"]


class FindingRow(Protocol):
    @property
    def client_name(self) -> str: ...

    @property
    def service_type(self) -> str: ...

    @property
    def service_year(self) -> str: ...

    @property
    def fee_million_krw(self) -> str: ...

    @property
    def risk_level(self) -> RiskLevel: ...

    @property
    def reason(self) -> str: ...


def risk_counts(findings: tuple[FindingRow, ...]) -> dict[str, int]:
    return {
        level: sum(1 for finding in findings if finding.risk_level == level)
        for level in risk_levels()
    }


def render_markdown(findings: tuple[FindingRow, ...]) -> str:
    counts = risk_counts(findings)
    lines = [
        "# 독립성 충돌 스크리닝 리포트",
        "",
        "이 리포트는 사용자 제공 CSV와 사용자 제공 JSON 룰셋으로 만든 1차 triage입니다.",
        "최종 독립성 판단은 전문가 검토가 필요합니다.",
        "",
        "## 요약",
        "",
        f"- 고위험: {counts['고위험']}건",
        f"- 추가 검토 필요: {counts['추가 검토 필요']}건",
        f"- 낮음: {counts['낮음']}건",
        "",
        "## 상세",
        "",
        "| 고객 | 용역 유형 | 연도 | 보수(백만원) | 위험도 | 사유 |",
        "|---|---|---:|---:|---|---|",
    ]
    for finding in findings:
        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_table_cell(finding.client_name),
                    markdown_table_cell(finding.service_type),
                    markdown_table_cell(finding.service_year),
                    markdown_table_cell(finding.fee_million_krw),
                    markdown_table_cell(finding.risk_level),
                    markdown_table_cell(finding.reason),
                ]
            )
            + " |"
        )
    if not findings:
        lines.append(
            "| 해당 없음 | - | - | - | 낮음 | "
            "감사 고객과 매칭되는 비감사용역이 없습니다. |"
        )
    lines.extend(
        [
            "",
            "## 추가 검토 필요",
            "",
            "- 고위험 또는 추가 검토 필요 항목은 계약 원문, 독립성 승인 이력, "
            "네트워크 법인 관여 여부를 확인해야 합니다.",
            "- 입력 파일에 없는 고객·계약은 평가하지 않았습니다.",
        ]
    )
    return "\n".join(lines)


def risk_levels() -> tuple[RiskLevel, RiskLevel, RiskLevel]:
    return ("고위험", "추가 검토 필요", "낮음")


def markdown_table_cell(value: str) -> str:
    collapsed = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return collapsed.replace("\\", "\\\\").replace("|", "\\|")
