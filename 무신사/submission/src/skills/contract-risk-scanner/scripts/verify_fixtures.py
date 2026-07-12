#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Optional, TypedDict


SKILL_DIR: Final = Path(__file__).resolve().parents[1]
SCANNER: Final = SKILL_DIR / "scripts" / "scan_contract.py"


class Finding(TypedDict):
    clause: str
    rule_id: str
    risk: str


class ScanOutput(TypedDict):
    source: str
    count: int
    findings: list[Finding]


@dataclass(frozen=True)
class ScanExpectation:
    name: str
    fixture: Path
    expected_count: int
    expected_rule_ids: tuple[str, ...]
    min_risk: Optional[str] = None
    expected_clauses: tuple[str, ...] = ()


def run_scan(contract: Path, min_risk: Optional[str] = None) -> ScanOutput:
    command = [sys.executable, str(SCANNER), str(contract), "--format", "json"]
    if min_risk is not None:
        command.extend(["--min-risk", min_risk])
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    parsed: ScanOutput = json.loads(result.stdout)
    return parsed


def assert_scan(expectation: ScanExpectation) -> None:
    output = run_scan(expectation.fixture, expectation.min_risk)
    rule_ids = tuple(finding["rule_id"] for finding in output["findings"])
    clauses = tuple(finding["clause"] for finding in output["findings"])

    assert output["count"] == expectation.expected_count, expectation.name
    assert rule_ids == expectation.expected_rule_ids, expectation.name
    if expectation.expected_clauses:
        assert clauses == expectation.expected_clauses, expectation.name


def test_documented_fixtures() -> None:
    fixtures = SKILL_DIR / "fixtures"
    expectations = (
        ScanExpectation(
            name="sample A all risks",
            fixture=fixtures / "sample_contract_01.md",
            expected_count=7,
            expected_rule_ids=(
                "R01_multihoming",
                "R02_mfn",
                "R03_promo_cost",
                "R04_return",
                "R05_biz_info",
                "R06_settlement_delay",
                "R07_price_deduction",
            ),
        ),
        ScanExpectation(
            name="sample A high risks only",
            fixture=fixtures / "sample_contract_01.md",
            expected_count=3,
            expected_rule_ids=("R01_multihoming", "R02_mfn", "R03_promo_cost"),
            min_risk="상",
        ),
        ScanExpectation(
            name="sample B cleaned high risks",
            fixture=fixtures / "sample_contract_02.md",
            expected_count=0,
            expected_rule_ids=(),
            min_risk="상",
        ),
        ScanExpectation(
            name="sample B intentional baseline false positives",
            fixture=fixtures / "sample_contract_02.md",
            expected_count=3,
            expected_rule_ids=("R04_return", "R05_biz_info", "R06_settlement_delay"),
        ),
        ScanExpectation(
            name="sample C mixed contract",
            fixture=fixtures / "sample_contract_03.md",
            expected_count=3,
            expected_rule_ids=("R01_multihoming", "R06_settlement_delay", "R07_price_deduction"),
            expected_clauses=("제3조 (공급)", "제5조 (대금 지급)", "제5조의2 (공제)"),
        ),
        ScanExpectation(
            name="sample C high risks only",
            fixture=fixtures / "sample_contract_03.md",
            expected_count=1,
            expected_rule_ids=("R01_multihoming",),
            min_risk="상",
        ),
        ScanExpectation(
            name="plain text fallback",
            fixture=fixtures / "sample_plain_clauses.txt",
            expected_count=2,
            expected_rule_ids=("R01_multihoming", "R03_promo_cost"),
            expected_clauses=("문단 1", "문단 2"),
        ),
    )
    for expectation in expectations:
        assert_scan(expectation)


def test_law_article_reference_does_not_split_clause() -> None:
    with tempfile.TemporaryDirectory() as directory:
        contract = Path(directory) / "law_reference_contract.md"
        contract.write_text(
            "\n".join(
                (
                    "제1조 (반품)",
                    "반품은 관계 법령이 정한 사유와",
                    "제10조에 따른 반품 사전 서면약정 범위 내에서만 가능하다.",
                    "대규모유통업법 제10조 등 관계 법령도 함께 확인한다.",
                    "사전 서면약정 범위 내에서만 가능하다.",
                    "",
                    "제2조 (판매 채널)",
                    "브랜드는 경쟁 플랫폼에 입점할 수 없다.",
                )
            ),
            encoding="utf-8",
        )

        output = run_scan(contract)
        clauses = tuple(finding["clause"] for finding in output["findings"])

    assert output["count"] == 2
    assert set(clauses) == {"제1조 (반품)", "제2조 (판매 채널)"}


def test_realistic_header_variants_are_reported_as_clause_labels() -> None:
    with tempfile.TemporaryDirectory() as directory:
        temp_dir = Path(directory)
        scenarios = (
            ScanExpectation(
                name="unparenthesized title header",
                fixture=temp_dir / "unparenthesized_title.md",
                expected_count=1,
                expected_rule_ids=("R01_multihoming",),
                expected_clauses=("제1조 판매 채널",),
            ),
            ScanExpectation(
                name="colon title header",
                fixture=temp_dir / "colon_title.md",
                expected_count=1,
                expected_rule_ids=("R02_mfn",),
                expected_clauses=("제2조: 판매가격",),
            ),
            ScanExpectation(
                name="bracket title header",
                fixture=temp_dir / "bracket_title.md",
                expected_count=1,
                expected_rule_ids=("R03_promo_cost",),
                expected_clauses=("제3조 [판매촉진]",),
            ),
        )
        scenarios[0].fixture.write_text(
            "제1조 판매 채널\n브랜드는 경쟁 플랫폼에 입점할 수 없다.",
            encoding="utf-8",
        )
        scenarios[1].fixture.write_text(
            "제2조: 판매가격\n브랜드는 타 채널보다 낮은 최저가를 보장한다.",
            encoding="utf-8",
        )
        scenarios[2].fixture.write_text(
            "제3조 [판매촉진]\n브랜드는 행사 비용 부담 및 판촉비를 부담한다.",
            encoding="utf-8",
        )

        for scenario in scenarios:
            assert_scan(scenario)


def test_missing_file_returns_exit_2() -> None:
    result = subprocess.run(
        [sys.executable, str(SCANNER), str(SKILL_DIR / "fixtures" / "missing.md")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "계약서 파일을 찾을 수 없습니다" in result.stderr


def test_empty_file_returns_zero_findings() -> None:
    with tempfile.TemporaryDirectory() as directory:
        contract = Path(directory) / "empty.md"
        contract.write_text("", encoding="utf-8")

        output = run_scan(contract)

    assert output["count"] == 0
    assert output["findings"] == []


def main() -> int:
    test_documented_fixtures()
    test_law_article_reference_does_not_split_clause()
    test_realistic_header_variants_are_reported_as_clause_labels()
    test_missing_file_returns_exit_2()
    test_empty_file_returns_zero_findings()
    print("fixture verification passed: 13 scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
