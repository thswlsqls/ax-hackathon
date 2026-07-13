from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "src" / "bin" / "independence_screen.py"
PYTHON = sys.executable


def run_cli(*args: str, cwd: Path = PLUGIN_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(SCRIPT), *args],
        cwd=cwd,
        capture_output=True,
        check=False,
        text=True,
    )


def run_screening(
    input_paths: tuple[str, str, str], *extra_args: str,
) -> subprocess.CompletedProcess[str]:
    audit_clients, non_audit_services, rules = input_paths
    return run_cli(
        "--audit-clients",
        audit_clients,
        "--non-audit-services",
        non_audit_services,
        "--rules",
        rules,
        *extra_args,
    )


def test_markdown_report_when_documented_example_is_run() -> None:
    # Given: the example inputs documented for the plugin CLI.

    # When: the CLI is run through Python.
    result = run_screening(
        (
            "src/examples/audit_clients.csv",
            "src/examples/non_audit_services.csv",
            "src/examples/independence_rules.json",
        ),
        "--format",
        "markdown",
    )

    # Then: it succeeds and reports the expected risk summary and high-risk service.
    assert result.returncode == 0, result.stderr
    assert "# 독립성 충돌 스크리닝 리포트" in result.stdout
    assert "고위험: 1건" in result.stdout
    assert "추가 검토 필요: 2건" in result.stdout
    assert "financial_system_implementation" in result.stdout


def test_missing_service_columns_exit_2_when_services_csv_is_malformed(tmp_path: Path) -> None:
    # Given: a services CSV that omits three required service columns.
    malformed_services = tmp_path / "malformed_services.csv"
    _ = malformed_services.write_text(
        "\n".join(
            [
                "client_id,client_name,service_type",
                "A001,상장제조 주식회사,financial_system_implementation",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    # When: the CLI is run with the malformed services file.
    result = run_screening(
        (
            "src/examples/audit_clients.csv",
            os.fspath(malformed_services),
            "src/examples/independence_rules.json",
        )
    )

    # Then: it exits with the documented input error code and names every missing column.
    assert result.returncode == 2
    assert "service_description" in result.stderr
    assert "service_year" in result.stderr
    assert "fee_million_krw" in result.stderr


def test_string_valued_rules_exit_2_when_rules_json_is_malformed(tmp_path: Path) -> None:
    # Given: a rules file that uses a string where a list of strings is required.
    malformed_rules = tmp_path / "malformed_rules.json"
    _ = malformed_rules.write_text(
        """
{
  "prohibited_service_types": "financial_system_implementation",
  "review_service_types": ["tax_advisory"],
  "network_service_keywords": ["network"]
}
""".strip(),
        encoding="utf-8",
    )

    # When: the CLI is run with the malformed rules file.
    result = run_screening(
        (
            "src/examples/audit_clients.csv",
            "src/examples/non_audit_services.csv",
            os.fspath(malformed_rules),
        )
    )

    # Then: it fails at the JSON trust boundary instead of silently downgrading risk.
    assert result.returncode == 2
    assert "prohibited_service_types" in result.stderr
    assert "list of strings" in result.stderr


def test_help_prints_usage_when_help_flag_is_passed() -> None:
    # Given: the CLI entry point.
    # When: help is requested.
    result = run_cli("--help")

    # Then: it prints usage without treating --help as a missing-value option.
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "--audit-clients" in result.stdout
    assert "--non-audit-services" in result.stdout
    assert "--rules" in result.stdout


AUDIT_HEADER = "client_id,client_name,audit_year"
SERVICE_HEADER = (
    "client_id,client_name,service_type,service_description,service_year,fee_million_krw"
)


def _write(path: Path, lines: tuple[str, ...]) -> str:
    _ = path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return os.fspath(path)


def _write_json(path: Path, obj: object) -> str:
    import json

    _ = path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return os.fspath(path)


def _rules(
    prohibited: tuple[str, ...] = ("financial_system_implementation",),
    review: tuple[str, ...] = ("tax_advisory",),
    keywords: tuple[str, ...] = ("네트워크", "shared brand"),
) -> dict[str, tuple[str, ...]]:
    return {"prohibited_service_types": prohibited, "review_service_types": review,
            "network_service_keywords": keywords}


def _default_rules(path: Path) -> str:
    return _write_json(path, _rules())


def test_service_priority_is_high_when_type_is_both_prohibited_and_review(tmp_path: Path) -> None:
    # Given: a rule set that lists the same service type as both prohibited and review-only.
    audit = _write(tmp_path / "a.csv", (AUDIT_HEADER, "A001,감사고객,2025"))
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, "A001,감사고객,dual_type,겹치는 유형,2025,10"),
    )
    rules = _write_json(
        tmp_path / "r.json",
        _rules(prohibited=("dual_type",), review=("dual_type",)),
    )

    # When: the CLI screens the overlapping service.
    result = run_screening((audit, services, rules))

    # Then: the prohibited rule wins so the row is high risk, never downgraded to review.
    assert result.returncode == 0, result.stderr
    assert "고위험: 1건" in result.stdout
    assert "추가 검토 필요: 0건" in result.stdout


def test_network_keyword_match_is_case_insensitive(tmp_path: Path) -> None:
    # Given: a mixed-case keyword and a description that differs only in letter case.
    audit = _write(tmp_path / "a.csv", (AUDIT_HEADER, "A001,감사고객,2025"))
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, "A001,감사고객,data_analytics,SHARED BRAND collaboration,2025,10"),
    )
    rules = _default_rules(tmp_path / "r.json")

    # When: the description case does not match the keyword case.
    result = run_screening((audit, services, rules))

    # Then: the keyword still triggers a review because matching is case-insensitive.
    assert result.returncode == 0, result.stderr
    assert "추가 검토 필요: 1건" in result.stdout
    assert "네트워크/공유 브랜드" in result.stdout


def test_low_risk_row_when_no_rule_is_triggered(tmp_path: Path) -> None:
    # Given: a matched service whose type and description trigger no rule.
    audit = _write(tmp_path / "a.csv", (AUDIT_HEADER, "A001,감사고객,2025"))
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, "A001,감사고객,brochure_design,단순 브로슈어 디자인,2025,5"),
    )
    rules = _default_rules(tmp_path / "r.json")

    # When: the CLI screens the untriggered service.
    result = run_screening((audit, services, rules))

    # Then: it is classified low and never described as "permitted".
    assert result.returncode == 0, result.stderr
    assert "낮음: 1건" in result.stdout
    assert "허용" not in result.stdout


def test_non_audit_client_service_is_excluded_when_client_id_is_not_audit_client(
    tmp_path: Path,
) -> None:
    # Given: a prohibited service for a client that is NOT an audit client.
    audit = _write(tmp_path / "a.csv", (AUDIT_HEADER, "A001,감사고객,2025"))
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, "Z999,비감사고객,financial_system_implementation,ERP 구축,2025,100"),
    )
    rules = _default_rules(tmp_path / "r.json")

    # When: the CLI screens a service tied only to a non-audit client.
    result = run_screening((audit, services, rules))

    # Then: the empty-report placeholder row is emitted, not a high-risk finding.
    assert result.returncode == 0, result.stderr
    assert "고위험: 0건" in result.stdout
    assert "해당 없음" in result.stdout
    assert "비감사고객" not in result.stdout


def test_whitespace_in_client_id_is_stripped_before_matching(tmp_path: Path) -> None:
    # Given: a service whose client_id carries surrounding whitespace.
    audit = _write(tmp_path / "a.csv", (AUDIT_HEADER, "A001,감사고객,2025"))
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, " A001 ,감사고객,tax_advisory,국제조세 자문,2025,20"),
    )
    rules = _default_rules(tmp_path / "r.json")

    # When: the CLI matches audit clients to services.
    result = run_screening((audit, services, rules))

    # Then: the padded id is stripped, so the service matches and is screened as review.
    assert result.returncode == 0, result.stderr
    assert "추가 검토 필요: 1건" in result.stdout


def test_missing_audit_columns_exit_2_when_audit_csv_is_malformed(tmp_path: Path) -> None:
    # Given: an audit CSV that omits the audit_year column.
    audit = _write(tmp_path / "a.csv", ("client_id,client_name", "A001,감사고객"))
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, "A001,감사고객,tax_advisory,자문,2025,20"),
    )
    rules = _default_rules(tmp_path / "r.json")

    # When: the CLI is run with the malformed audit file.
    result = run_screening((audit, services, rules))

    # Then: it exits with the input error code and names the missing column.
    assert result.returncode == 2
    assert "audit_year" in result.stderr


def test_nonexistent_input_file_exits_2(tmp_path: Path) -> None:
    # Given: an audit path that does not exist.
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, "A001,감사고객,tax_advisory,자문,2025,20"),
    )
    rules = _default_rules(tmp_path / "r.json")

    # When: the CLI is pointed at a missing file.
    result = run_screening((os.fspath(tmp_path / "missing.csv"), services, rules))

    # Then: the OSError is caught and reported as an input error, not an uncaught traceback.
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_broken_json_syntax_exits_2(tmp_path: Path) -> None:
    # Given: a rules file that is not valid JSON.
    audit = _write(tmp_path / "a.csv", (AUDIT_HEADER, "A001,감사고객,2025"))
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, "A001,감사고객,tax_advisory,자문,2025,20"),
    )
    broken = tmp_path / "r.json"
    _ = broken.write_text("{ not valid json", encoding="utf-8")

    # When: the CLI parses the broken rules file.
    result = run_screening((audit, services, os.fspath(broken)))

    # Then: the JSON decode error is caught at the trust boundary and mapped to exit 2.
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_empty_rule_string_exits_2(tmp_path: Path) -> None:
    # Given: a rules file with an empty string inside a rule list.
    audit = _write(tmp_path / "a.csv", (AUDIT_HEADER, "A001,감사고객,2025"))
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, "A001,감사고객,tax_advisory,자문,2025,20"),
    )
    rules = _write_json(
        tmp_path / "r.json",
        {
            "prohibited_service_types": [""],
            "review_service_types": ["tax_advisory"],
            "network_service_keywords": ["네트워크"],
        },
    )

    # When: the CLI validates the rule strings.
    result = run_screening((audit, services, rules))

    # Then: the empty rule token is rejected rather than silently matching every service type.
    assert result.returncode == 2
    assert "must not be empty" in result.stderr


def test_unknown_format_exits_1(tmp_path: Path) -> None:
    # Given: valid inputs but an unsupported --format value.
    audit = _write(tmp_path / "a.csv", (AUDIT_HEADER, "A001,감사고객,2025"))
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, "A001,감사고객,tax_advisory,자문,2025,20"),
    )
    rules = _default_rules(tmp_path / "r.json")

    # When: an unknown output format is requested.
    result = run_screening((audit, services, rules), "--format", "json")

    # Then: the CLI refuses the argument instead of emitting an unexpected format.
    assert result.returncode == 1
    assert "markdown" in result.stderr


def test_missing_required_argument_exits_1() -> None:
    # Given: a call that omits the required rules and services flags.
    # When: the CLI parses incomplete arguments.
    result = run_cli("--audit-clients", "src/examples/audit_clients.csv")

    # Then: it names the missing flags and exits with the usage error code.
    assert result.returncode == 1
    assert "--non-audit-services" in result.stderr
    assert "--rules" in result.stderr


def test_short_service_row_exits_2_when_required_cell_is_missing(tmp_path: Path) -> None:
    # Given: a services CSV row with fewer cells than the required header.
    audit = _write(tmp_path / "a.csv", (AUDIT_HEADER, "A001,감사고객,2025"))
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, "A001,감사고객,tax_advisory"),
    )
    rules = _default_rules(tmp_path / "r.json")

    # When: the CLI parses the malformed row.
    result = run_screening((audit, services, rules))

    # Then: it reports a controlled input error instead of crashing while stripping None.
    assert result.returncode == 2
    assert "row 2" in result.stderr
    assert "service_description" in result.stderr


def test_blank_required_csv_value_exits_2(tmp_path: Path) -> None:
    # Given: a service row with a blank required value after whitespace normalization.
    audit = _write(tmp_path / "a.csv", (AUDIT_HEADER, "A001,감사고객,2025"))
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, "A001,감사고객,   ,자문 설명,2025,20"),
    )
    rules = _default_rules(tmp_path / "r.json")

    # When: the CLI parses the row.
    result = run_screening((audit, services, rules))

    # Then: the blank service_type is rejected at the CSV trust boundary.
    assert result.returncode == 2
    assert "service_type" in result.stderr
    assert "must not be empty" in result.stderr


def test_unknown_option_exits_1_even_when_required_arguments_are_present() -> None:
    # Given: valid required arguments plus an unsupported option.
    # When: the CLI receives a typo-like flag.
    result = run_screening(
        (
            "src/examples/audit_clients.csv",
            "src/examples/non_audit_services.csv",
            "src/examples/independence_rules.json",
        ),
        "--unknown-option",
        "value",
    )

    # Then: the parser rejects the unknown option rather than silently ignoring it.
    assert result.returncode == 1
    assert "unknown option" in result.stderr


def test_markdown_format_is_default_when_format_flag_is_omitted() -> None:
    # Given: valid documented example inputs.

    # When: the CLI is run without an explicit --format flag.
    result = run_screening(
        (
            "src/examples/audit_clients.csv",
            "src/examples/non_audit_services.csv",
            "src/examples/independence_rules.json",
        )
    )

    # Then: it defaults to Markdown and emits the report.
    assert result.returncode == 0, result.stderr
    assert "# 독립성 충돌 스크리닝 리포트" in result.stdout
    assert "## 상세" in result.stdout


def test_duplicate_cli_flag_exits_1(tmp_path: Path) -> None:
    # Given: valid inputs with the audit CSV flag supplied twice.
    extra_audit = _write(tmp_path / "a.csv", (AUDIT_HEADER, "A999,다른고객,2025"))

    # When: the singleton --audit-clients option is duplicated.
    result = run_cli(
        "--audit-clients",
        "src/examples/audit_clients.csv",
        "--audit-clients",
        extra_audit,
        "--non-audit-services",
        "src/examples/non_audit_services.csv",
        "--rules",
        "src/examples/independence_rules.json",
    )

    # Then: the parser rejects the ambiguous invocation instead of using the last value.
    assert result.returncode == 1
    assert "duplicate option" in result.stderr
    assert "--audit-clients" in result.stderr


def test_extra_service_row_cell_exits_2_when_csv_has_surplus_value(tmp_path: Path) -> None:
    # Given: a services CSV row with more cells than the header declares.
    audit = _write(tmp_path / "a.csv", (AUDIT_HEADER, "A001,감사고객,2025"))
    services = _write(
        tmp_path / "s.csv",
        (SERVICE_HEADER, "A001,감사고객,tax_advisory,자문 설명,2025,20,unexpected"),
    )
    rules = _default_rules(tmp_path / "r.json")

    # When: the CLI parses the malformed row.
    result = run_screening((audit, services, rules))

    # Then: it reports a controlled input error rather than ignoring the surplus value.
    assert result.returncode == 2
    assert "row 2" in result.stderr
    assert "unexpected extra fields" in result.stderr
