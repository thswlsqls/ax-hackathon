#!/usr/bin/env python3
"""Analyze public MTS incidents and propose deterministic stability scenarios."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Final

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
if __package__ in {None, ""}:
    __package__ = "scripts"

from . import safe_filesystem as sf  # noqa: E402
from .incident_schema import (  # noqa: E402
    JSON_DECODE,
    AnalysisResult,
    AnnualEvidence,
    Config,
    Incident,
    JsonMap,
    JsonValue,
    Playbook,
    Scenario,
)


class CliArgs(argparse.Namespace):
    input: str = ""
    config: str = ""
    json_out: str | None = None


SKILL_ROOT: Final = os.path.dirname(SCRIPT_DIR)
DEFAULT_INPUT: Final = os.path.join(SKILL_ROOT, "data", "incidents.sample.json")
DEFAULT_CONFIG: Final = os.path.join(SKILL_ROOT, "config", "stability-config.json")
PERIOD_RE: Final = re.compile(r"^(\d{4})(?:Q([1-4]))?$")
INCIDENT_TEXT_FIELDS: Final = ("id", "date", "service", "pattern", "cause", "source", "source_url")


class AnalysisError(Exception):
    pass


class ConfigError(AnalysisError):
    pass


class IncidentDataError(AnalysisError):
    pass


def _is_text(value: JsonValue, require_content: bool = True) -> bool:
    if not isinstance(value, str) or (require_content and not value.strip()):
        return False
    if any(unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"} for character in value):
        return False
    try:
        _ = value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def load(path: str) -> JsonValue:
    with open(path, encoding="utf-8") as source:
        value = JSON_DECODE(source.read())
    return value


def _validated_playbook(patterns: JsonValue | Playbook) -> Playbook:
    if not isinstance(patterns, dict) or not patterns:
        raise ConfigError("config.patterns must be a non-empty object")
    validated: Playbook = {}
    for key, value in patterns.items():
        if not _is_text(key) or not isinstance(value, dict):
            raise ConfigError("each config pattern must have a non-empty string key and object value")
        label = value.get("label")
        tests = value.get("recommended_tests")
        if not isinstance(label, str) or not _is_text(label):
            raise ConfigError(f"config.patterns.{key}.label must be a non-empty string")
        if (
            not isinstance(tests, list)
            or not tests
            or any(not isinstance(test, str) or not _is_text(test) for test in tests)
        ):
            raise ConfigError(
                f"config.patterns.{key}.recommended_tests must be a non-empty string array",
            )
        validated[key] = {
            "label": label,
            "recommended_tests": [test for test in tests if isinstance(test, str)],
        }
    return validated


def load_config(path: str = DEFAULT_CONFIG) -> Config:
    """Load and validate the configured failure-pattern playbook."""
    config = load(path)
    if not isinstance(config, dict):
        raise ConfigError("config must be a JSON object")
    return {"patterns": _validated_playbook(config.get("patterns"))}


try:
    _loaded_playbook = load_config(DEFAULT_CONFIG)["patterns"]
except (AnalysisError, json.JSONDecodeError, OSError, UnicodeError):
    _loaded_playbook = {}
PATTERN_PLAYBOOK: Final[Playbook] = _loaded_playbook


def _validated_incidents(data: JsonValue, playbook: Playbook) -> list[Incident]:
    if not isinstance(data, dict):
        raise IncidentDataError("incident input must be a JSON object")
    incidents = data.get("incidents")
    if not isinstance(incidents, list):
        raise IncidentDataError("incidents must be an array")
    seen_ids: set[str] = set()
    validated: list[Incident] = []
    for index, incident in enumerate(incidents):
        prefix = f"incidents[{index}]"
        if not isinstance(incident, dict):
            raise IncidentDataError(f"{prefix} must be an object")
        text_fields: dict[str, str] = {}
        for field in INCIDENT_TEXT_FIELDS:
            value = incident.get(field)
            if not isinstance(value, str) or not _is_text(value):
                raise IncidentDataError(f"{prefix}.{field} must be a non-empty string")
            text_fields[field] = value
        incident_id = text_fields["id"]
        if incident_id in seen_ids:
            raise IncidentDataError(f"duplicate incident id: {incident_id}")
        seen_ids.add(incident_id)
        if text_fields["pattern"] not in playbook:
            raise IncidentDataError(f"{prefix}.pattern is not defined in config")
        duration = incident.get("duration_min")
        if duration is not None and (
            isinstance(duration, bool) or not isinstance(duration, int) or duration < 0
        ):
            raise IncidentDataError(f"{prefix}.duration_min must be null or a non-negative integer")
        validated.append({
            "id": incident_id,
            "date": text_fields["date"],
            "service": text_fields["service"],
            "pattern": text_fields["pattern"],
            "cause": text_fields["cause"],
            "source": text_fields["source"],
            "source_url": text_fields["source_url"],
            "duration_min": duration,
        })
    return validated


def _validated_annual_counts(data: JsonMap) -> list[tuple[str, int]]:
    annual_counts = data.get("annual_counts")
    if not isinstance(annual_counts, dict):
        raise IncidentDataError("annual_counts must be an object")
    counts = annual_counts.get("counts")
    if not isinstance(counts, dict):
        raise IncidentDataError("annual_counts.counts must be an object")
    validated: list[tuple[tuple[int, int], str, int]] = []
    for period, count in counts.items():
        match = PERIOD_RE.fullmatch(period) if _is_text(period) else None
        if match is None:
            raise IncidentDataError("annual count periods must use YYYY or YYYYQ1..YYYYQ4")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise IncidentDataError(f"annual_counts.counts.{period} must be a non-negative integer")
        quarter = int(match.group(2)) if match.group(2) else 0
        validated.append(((int(match.group(1)), quarter), period, count))
    return [(period, count) for _, period, count in sorted(validated)]


def _text_field(container: JsonMap, field: str, default: str = "") -> str:
    value = container.get(field, default)
    if not isinstance(value, str) or not _is_text(value, require_content=False):
        raise IncidentDataError(f"{field} must be a UTF-8 string")
    return value


def analyze(data: JsonValue, playbook: Playbook | None = None) -> AnalysisResult:
    """Return factual aggregates and config-derived recommendations."""
    if not isinstance(data, dict):
        raise IncidentDataError("incident input must be a JSON object")
    active_playbook = _validated_playbook(PATTERN_PLAYBOOK if playbook is None else playbook)
    incidents = _validated_incidents(data, active_playbook)
    trend = _validated_annual_counts(data)
    meta = data.get("meta", {})
    annual_counts = data["annual_counts"]
    if not isinstance(meta, dict):
        raise IncidentDataError("meta must be an object")
    if not isinstance(annual_counts, dict):
        raise IncidentDataError("annual_counts must be an object")
    annual_evidence: AnnualEvidence = {
        "basis": _text_field(annual_counts, "basis"), "source": _text_field(annual_counts, "source"),
        "source_url": _text_field(annual_counts, "source_url")}
    pattern_counts = Counter(incident["pattern"] for incident in incidents)
    ranked_patterns = sorted(pattern_counts.items(), key=lambda item: (-item[1], item[0]))
    scenarios: list[Scenario] = [{
            "pattern": pattern, "label": active_playbook[pattern]["label"],
            "observed_incidents": count,
            "recommended_tests": list(active_playbook[pattern]["recommended_tests"])}
        for pattern, count in ranked_patterns
    ]
    return {
        "pattern_distribution": dict(sorted(pattern_counts.items())),
        "annual_trend": trend,
        "scenarios": scenarios,
        "incident_total": len(incidents),
        "evidence": {
            "subject": _text_field(meta, "subject", "N/A"),
            "annual_counts": annual_evidence,
            "incident_source_urls": sorted({incident["source_url"] for incident in incidents}),
        },
    }


def render(_data: JsonValue, result: AnalysisResult, playbook: Playbook | None = None) -> str:
    """Render public facts separately from config-derived interpretation."""
    _ = PATTERN_PLAYBOOK if playbook is None else _validated_playbook(playbook)
    annual_evidence = result["evidence"]["annual_counts"]
    out = ["=" * 64, "MTS Stability Guard — 재발방지 분석 리포트", "=" * 64]
    out.append(f"[사실] 대상: {result['evidence']['subject']}")
    out.extend(("", f"[사실] 연도별 장애 추세 ({annual_evidence['basis']})"))
    previous_full_year = None
    for period, count in result["annual_trend"]:
        arrow = ""
        if "Q" not in period and previous_full_year is not None:
            arrow = "  ↑" if count > previous_full_year else ("  ↓" if count < previous_full_year else "  →")
        out.append(f"  {period}: {count}건{arrow}")
        if "Q" not in period:
            previous_full_year = count
    if annual_evidence["source"]:
        out.append(f"  출처: {annual_evidence['source']}")
    if annual_evidence["source_url"]:
        out.append(f"  출처 URL: {annual_evidence['source_url']}")
    out.extend(("", f"[사실] 분석한 개별 사건: {result['incident_total']}건", "[사실] 실패 패턴 분포:"))
    for pattern, count in result["pattern_distribution"].items():
        out.append(f"  - {pattern}: {count}건")
    out.extend(("", "[해석] 우선순위 재발방지 시나리오 (우세 패턴 순):"))
    for index, scenario in enumerate(result["scenarios"], 1):
        out.append(f"  {index}. {scenario['label']} — 관측 {scenario['observed_incidents']}건")
        out.extend(f"       · {test}" for test in scenario["recommended_tests"])
    out.extend((
        "",
        "[주의] 건수는 집계 창에 따라 다름(RFARS 2022~2025=37건 vs 2022.1~2026.3=42건).",
        "[주의] 시나리오는 이 스킬의 해석이며, 시연은 공개 이력+모의 시스템으로 한정한다.",
        "=" * 64,
    ))
    return "\n".join(out)


def _write_json_atomic(path: str, result: AnalysisResult) -> None:
    sf.write_text(Path(path), json.dumps(result, ensure_ascii=False, indent=2) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="공개 장애 이력에서 재발방지 테스트 시나리오 생성")
    _ = parser.add_argument("--input", default=DEFAULT_INPUT, help="장애 이력 JSON 경로")
    _ = parser.add_argument("--config", default=DEFAULT_CONFIG, help="분석 정책 JSON 경로")
    _ = parser.add_argument("--json-out", help="기계가 읽는 JSON 리포트 저장 경로")
    args = parser.parse_args(argv, namespace=CliArgs())
    try:
        try:
            data = load(args.input)
        except RecursionError as error:
            raise IncidentDataError("incident JSON exceeds maximum nesting depth") from error
        playbook = load_config(args.config)["patterns"]
        result = analyze(data, playbook=playbook)
        report = render(data, result, playbook=playbook)
        output = report + "\n"
        _ = output.encode(sys.stdout.encoding or "utf-8")
        _ = sys.stdout.write(output)
        _ = sys.stdout.flush()
        if args.json_out:
            _write_json_atomic(args.json_out, result)
    except (AnalysisError, json.JSONDecodeError, OSError, UnicodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
