"""Typed JSON and incident-analysis domain records."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Final, TypedDict, Union

JsonValue = Union[str, int, float, bool, None, list["JsonValue"], dict[str, "JsonValue"]]
JsonMap = dict[str, JsonValue]
class PlaybookEntry(TypedDict):
    label: str
    recommended_tests: list[str]
Playbook = dict[str, PlaybookEntry]
class Config(TypedDict):
    patterns: Playbook
class Incident(TypedDict):
    id: str
    date: str
    service: str
    pattern: str
    cause: str
    source: str
    source_url: str
    duration_min: Union[int, None]
class Scenario(TypedDict):
    pattern: str
    label: str
    observed_incidents: int
    recommended_tests: list[str]
class AnnualEvidence(TypedDict):
    basis: str
    source: str
    source_url: str
class Evidence(TypedDict):
    subject: str
    annual_counts: AnnualEvidence
    incident_source_urls: list[str]
class AnalysisResult(TypedDict):
    pattern_distribution: dict[str, int]
    annual_trend: list[tuple[str, int]]
    scenarios: list[Scenario]
    incident_total: int
    evidence: Evidence


def _typed_decoder(decoder: Callable[[str], JsonValue]) -> Callable[[str], JsonValue]:
    return decoder


JSON_DECODE: Final = _typed_decoder(json.loads)
