#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from samil_independence.reporting import RiskLevel, render_markdown

REQUIRED_AUDIT_FIELDS: Final = ("client_id", "client_name", "audit_year")
REQUIRED_SERVICE_FIELDS: Final = (
    "client_id",
    "client_name",
    "service_type",
    "service_description",
    "service_year",
    "fee_million_krw",
)

HELP_TEXT: Final = (
    "Usage: python3 src/bin/independence_screen.py --audit-clients PATH "
    "--non-audit-services PATH --rules PATH [--format markdown]\n"
    "\n"
    "Options:\n"
    "  --audit-clients PATH        Audit client CSV path.\n"
    "  --non-audit-services PATH   Non-audit services CSV path.\n"
    "  --rules PATH                Independence rules JSON path.\n"
    "  --format markdown           Output format. Defaults to markdown.\n"
    "  -h, --help                  Show this help message.\n"
)


@dataclass(frozen=True)
class AuditClient:
    client_id: str
    client_name: str
    audit_year: str


@dataclass(frozen=True)
class NonAuditService:
    client_id: str
    client_name: str
    service_type: str
    service_description: str
    service_year: str
    fee_million_krw: str


@dataclass(frozen=True)
class IndependenceRules:
    prohibited_service_types: frozenset[str]
    review_service_types: frozenset[str]
    network_service_keywords: tuple[str, ...]


@dataclass(frozen=True)
class ScreeningFinding:
    client_name: str
    service_type: str
    service_year: str
    fee_million_krw: str
    risk_level: RiskLevel
    reason: str


@dataclass(frozen=True)
class CliArgs:
    audit_clients: Path
    non_audit_services: Path
    rules: Path


class InputFormatError(ValueError):
    def __init__(self, path: Path, missing_fields: tuple[str, ...]) -> None:
        super().__init__(f"{path} is missing required columns: {', '.join(missing_fields)}")


class CsvRowFormatError(ValueError):
    def __init__(self, path: Path, row_number: int, field: str, message: str) -> None:
        super().__init__(f"{path} row {row_number} field {field} {message}")


class RuleFormatError(ValueError):
    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path} has invalid rule format: {message}")


def load_audit_clients(path: Path) -> tuple[AuditClient, ...]:
    rows = read_csv(path, REQUIRED_AUDIT_FIELDS)
    return tuple(
        AuditClient(
            client_id=row["client_id"].strip(),
            client_name=row["client_name"].strip(),
            audit_year=row["audit_year"].strip(),
        )
        for row in rows
    )


def load_non_audit_services(path: Path) -> tuple[NonAuditService, ...]:
    rows = read_csv(path, REQUIRED_SERVICE_FIELDS)
    return tuple(
        NonAuditService(
            client_id=row["client_id"].strip(),
            client_name=row["client_name"].strip(),
            service_type=row["service_type"].strip(),
            service_description=row["service_description"].strip(),
            service_year=row["service_year"].strip(),
            fee_million_krw=row["fee_million_krw"].strip(),
        )
        for row in rows
    )


def read_csv(path: Path, required_fields: tuple[str, ...]) -> tuple[dict[str, str], ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        missing = tuple(field for field in required_fields if field not in fieldnames)
        if missing:
            raise InputFormatError(path=path, missing_fields=missing)
        rows: list[dict[str, str]] = []
        for row in reader:
            extra_values = row.get(None)
            if extra_values is not None:
                raise CsvRowFormatError(
                    path=path,
                    row_number=reader.line_num,
                    field="row",
                    message="has unexpected extra fields",
                )
            checked_row: dict[str, str] = {}
            for field in required_fields:
                value = row.get(field)
                if value is None:
                    raise CsvRowFormatError(
                        path=path,
                        row_number=reader.line_num,
                        field=field,
                        message="is missing",
                    )
                if not value.strip():
                    raise CsvRowFormatError(
                        path=path,
                        row_number=reader.line_num,
                        field=field,
                        message="must not be empty",
                    )
                checked_row[field] = value
            rows.append(checked_row)
        return tuple(rows)


def load_rules(path: Path) -> IndependenceRules:
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    rule_object = read_rule_object(raw, path)
    return IndependenceRules(
        prohibited_service_types=frozenset(
            read_rule_strings(rule_object, path, "prohibited_service_types")
        ),
        review_service_types=frozenset(
            read_rule_strings(rule_object, path, "review_service_types")
        ),
        network_service_keywords=tuple(
            read_rule_strings(rule_object, path, "network_service_keywords")
        ),
    )


def read_rule_object(raw: object, path: Path) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise RuleFormatError(path=path, message="root must be a JSON object")
    rule_object: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise RuleFormatError(path=path, message="rule field names must be strings")
        rule_object[key] = value
    return rule_object


def read_rule_strings(raw: dict[str, object], path: Path, field: str) -> tuple[str, ...]:
    value = raw.get(field)
    if not isinstance(value, list):
        raise RuleFormatError(path=path, message=f"{field} must be a list of strings")
    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise RuleFormatError(path=path, message=f"{field}[{index}] must be a string")
        stripped = item.strip()
        if not stripped:
            raise RuleFormatError(path=path, message=f"{field}[{index}] must not be empty")
        strings.append(stripped)
    return tuple(strings)


def screen(
    audit_clients: tuple[AuditClient, ...],
    services: tuple[NonAuditService, ...],
    rules: IndependenceRules,
) -> tuple[ScreeningFinding, ...]:
    audit_client_ids = frozenset(client.client_id for client in audit_clients)
    findings: list[ScreeningFinding] = []
    for service in services:
        if service.client_id not in audit_client_ids:
            continue
        risk_level, reason = classify_service(service, rules)
        findings.append(
            ScreeningFinding(
                client_name=service.client_name,
                service_type=service.service_type,
                service_year=service.service_year,
                fee_million_krw=service.fee_million_krw,
                risk_level=risk_level,
                reason=reason,
            )
        )
    return tuple(findings)


def classify_service(service: NonAuditService, rules: IndependenceRules) -> tuple[RiskLevel, str]:
    service_type = service.service_type
    description = service.service_description.lower()
    if service_type in rules.prohibited_service_types:
        return "고위험", "금지용역 룰셋에 포함된 서비스 유형입니다."
    if service_type in rules.review_service_types:
        return "추가 검토 필요", "사전 독립성 검토가 필요한 서비스 유형입니다."
    if any(keyword.lower() in description for keyword in rules.network_service_keywords):
        return "추가 검토 필요", "네트워크/공유 브랜드 관련 키워드가 설명에 포함되어 있습니다."
    return "낮음", "현재 룰셋에서 금지 또는 검토 트리거가 확인되지 않았습니다."


def parse_cli_args(argv: tuple[str, ...]) -> CliArgs:
    allowed_flags = ("--audit-clients", "--non-audit-services", "--rules", "--format")
    values: dict[str, str] = {}
    index = 0
    while index < len(argv):
        flag = argv[index]
        if not flag.startswith("--"):
            raise SystemExit(f"unexpected argument: {flag}")
        if flag not in allowed_flags:
            raise SystemExit(f"unknown option: {flag}")
        if flag in values:
            raise SystemExit(f"duplicate option: {flag}")
        next_index = index + 1
        if next_index >= len(argv):
            raise SystemExit(f"missing value for {flag}")
        values[flag] = argv[next_index]
        index += 2

    required_flags = ("--audit-clients", "--non-audit-services", "--rules")
    missing = tuple(flag for flag in required_flags if flag not in values)
    if missing:
        raise SystemExit(f"missing required arguments: {', '.join(missing)}")

    output_format = values.get("--format", "markdown")
    if output_format != "markdown":
        raise SystemExit("--format must be markdown")

    return CliArgs(
        audit_clients=Path(values["--audit-clients"]),
        non_audit_services=Path(values["--non-audit-services"]),
        rules=Path(values["--rules"]),
    )


def main() -> int:
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(HELP_TEXT)
        return 0

    args = parse_cli_args(tuple(sys.argv[1:]))
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
        print(str(error), file=sys.stderr)
        return 2
    findings = screen(audit_clients=audit_clients, services=services, rules=rules)
    print(render_markdown(findings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
