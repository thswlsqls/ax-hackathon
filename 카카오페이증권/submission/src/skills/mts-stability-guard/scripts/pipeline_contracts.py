"""Typed records and runtime boundary for pipeline orchestration."""

from __future__ import annotations

import importlib
from typing import Protocol, TypedDict, Union, runtime_checkable

from .incident_schema import AnalysisResult


class ChaosTally(TypedDict):
    filled: int
    deferred: int
    crashed: int
class ChaosScenario(TypedDict):
    pattern: str
    public_basis: str
    injected: str
    naive: ChaosTally
    guarded: ChaosTally
class AnalysisSummary(TypedDict):
    incident_total: int
    scenario_total: int
    dominant_pattern: Union[str, None]
class InputArtifacts(TypedDict):
    input: str
    config: str
class EmptyArtifacts(TypedDict):
    pass
ArtifactPaths = dict[str, Union[str, None]]
ChaosSummary = dict[str, Union[int, str]]
class PipelineState(TypedDict):
    run_id: str
    started_at: str
    finished_at: Union[str, None]
    status: str
    input_path: str
    config_path: str
    artifacts: ArtifactPaths
    analysis_summary: AnalysisSummary
    chaos_summary: ChaosSummary
    error: Union[str, None]
    input_artifacts: Union[InputArtifacts, EmptyArtifacts]
JsonOutput = Union[AnalysisResult, list[ChaosScenario], PipelineState]


@runtime_checkable
class ChaosModule(Protocol):
    def run(self) -> list[ChaosScenario]: ...


class ChaosContractError(RuntimeError):
    """The chaos module does not expose its typed runtime contract."""


def load_chaos_module() -> ChaosModule:
    module = importlib.import_module("demo.chaos_runner")
    if not isinstance(module, ChaosModule):
        raise ChaosContractError("demo.chaos_runner.run is unavailable")
    return module
