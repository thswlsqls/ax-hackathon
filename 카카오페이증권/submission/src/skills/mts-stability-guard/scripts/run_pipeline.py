#!/usr/bin/env python3
"""Orchestrate deterministic MTS stability analysis runs."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import FrameType
from typing import Final

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_INPUT_DIR = SKILL_ROOT.parents[2] / "input"
DEFAULT_OUTPUT_DIR = SKILL_ROOT.parents[2] / "output"
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

if __package__ in {None, ""}:
    __package__ = "scripts"

from . import analyze_incidents as ai  # noqa: E402
from . import incident_schema as schema  # noqa: E402
from . import pipeline_contracts as pc  # noqa: E402
from . import pipeline_memory as pm  # noqa: E402
from . import safe_filesystem as sf  # noqa: E402

chaos_runner: Final = pc.load_chaos_module()


class PipelineArgs(argparse.Namespace):
    input: str = ai.DEFAULT_INPUT
    config: str = ai.DEFAULT_CONFIG
    run_id: str = ""
    input_dir: str = str(DEFAULT_INPUT_DIR)
    output_dir: str = str(DEFAULT_OUTPUT_DIR)
    skip_chaos: bool = False


class RunError(Exception):
    """Report a safe pipeline contract error."""


PIPELINE_TIMEOUT_SECONDS: Final = 1.0


def _raise_timeout(_signum: int, _frame: FrameType | None) -> None:
    raise TimeoutError("pipeline execution timed out")


def _parse_run_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise RunError(
            "run id must contain only letters, numbers, dots, underscores, and hyphens",
        )
    if value in {".", ".."} or value.startswith(".") or ".." in value:
        raise RunError("run id must not be a relative path")
    return value


def _write_json(path: Path, value: pc.JsonOutput) -> None:
    sf.write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _input_artifacts(input_run_dir: Path) -> pc.InputArtifacts:
    return {"input": str(input_run_dir / "incidents.json"), "config": str(input_run_dir / "stability-config.json")}


def _snapshot_inputs(args: PipelineArgs, input_run_dir: Path) -> pc.InputArtifacts:
    input_source = Path(args.input)
    config_source = Path(args.config)
    with input_source.open(encoding="utf-8", newline="") as handle:
        input_text = handle.read()
    with config_source.open(encoding="utf-8", newline="") as handle:
        config_text = handle.read()
    artifacts = _input_artifacts(input_run_dir)
    sf.write_text(Path(artifacts["input"]), input_text)
    sf.write_text(Path(artifacts["config"]), config_text)
    return artifacts


def _reserve_run_dirs(input_run_dir: Path, run_dir: Path) -> None:
    try:
        sf.reserve_directories(run_dir, input_run_dir)
    except FileExistsError as exc:
        raise RunError(f"run id already exists: {run_dir.name}") from exc


def _analysis_summary(result: schema.AnalysisResult) -> pc.AnalysisSummary:
    scenarios = result["scenarios"]
    return {
        "incident_total": result["incident_total"], "scenario_total": len(scenarios),
        "dominant_pattern": scenarios[0]["pattern"] if scenarios else None,
    }


def _chaos_summary(results: list[pc.ChaosScenario]) -> pc.ChaosSummary:
    return {
        "scenario_total": len(results),
        "guarded_crashed_total": sum(item["guarded"]["crashed"] for item in results),
    }


def _state(run_id: str, input_path: str, config_path: str, artifacts: pc.ArtifactPaths,
           status: str, started_at: str) -> pc.PipelineState:
    return {
        "run_id": run_id, "started_at": started_at, "finished_at": None,
        "status": status, "input_path": str(input_path), "config_path": str(config_path),
        "artifacts": artifacts,
        "analysis_summary": {"incident_total": 0, "scenario_total": 0, "dominant_pattern": None},
        "chaos_summary": {}, "error": None, "input_artifacts": {},
    }


CHECKLIST_MAX_LINES: Final = 120


def _json_text(value: schema.JsonValue) -> str:
    return value if isinstance(value, str) else ""


def _incident_lines(data: schema.JsonValue) -> list[str]:
    if not isinstance(data, dict):
        return []
    incidents = data.get("incidents")
    if not isinstance(incidents, list):
        return []
    return [
        "".join((f"- {_json_text(item.get('date'))}: ",
                 f"{_json_text(item.get('title'))} ({_json_text(item.get('pattern'))}) ",
                 _json_text(item.get("source_url"))))
        for item in incidents if isinstance(item, dict)
    ]


def _render_checklist(
    data: schema.JsonValue,
    analysis: schema.AnalysisResult,
    chaos: list[pc.ChaosScenario],
    learned_context: str,
) -> str:
    header = [
        "# MTS Stability Guard Scenario Checklist",
        "",
        "## [사실]",
        f"- 분석 사건: {analysis['incident_total']}건",
        f"- 연도별 집계 기준: {analysis['evidence']['annual_counts']['basis']}",
        f"- 출처: {analysis['evidence']['annual_counts']['source']}",
    ]
    incident_lines = _incident_lines(data)
    tail = ["", "## [해석]"]
    for scenario in analysis["scenarios"]:
        tail.append("".join((f"- {scenario['pattern']}: {scenario['label']} ",
                             f"관측 {scenario['observed_incidents']}건")))
        tail.extend(f"  - {action}" for action in scenario["recommended_tests"])
    if chaos:
        tail.extend(("", "## [사실] Chaos before/after"))
        tail.extend("".join((f"- {item['pattern']}: before crashed={item['naive']['crashed']}, ",
                             f"after crashed={item['guarded']['crashed']}, ",
                             f"basis={item['public_basis']}")) for item in chaos)
    # learned_context는 여러 줄일 수 있으므로 실제 물리 줄 단위로 펼쳐
    # 줄 수를 정확히 센다.
    tail += ["", "## [학습]", *learned_context.split("\n")]

    # 고정 섹션([해석]·Chaos·[학습])은 항상 보존하고, 무한정 늘어날 수 있는 사건 목록만
    # 길이 상한에 맞춰 잘라낸다(상한 초과 입력에서도 tail 섹션이 사라지지 않도록).
    budget = CHECKLIST_MAX_LINES - len(header) - len(tail)
    if len(incident_lines) > budget:
        omitted = len(incident_lines) - max(0, budget - 1)
        incident_lines = incident_lines[: max(0, budget)]
        if incident_lines:
            incident_lines[-1] = f"- … 외 {omitted}건 생략(길이 상한 {CHECKLIST_MAX_LINES}줄)"
    return "\n".join(header + incident_lines + tail) + "\n"


def _success_memory_line(
    run_id: str,
    analysis_summary: pc.AnalysisSummary,
    chaos_summary: pc.ChaosSummary,
) -> str:
    return (
        f"run={run_id} status=succeeded incidents={analysis_summary['incident_total']} "
        f"scenarios={analysis_summary['scenario_total']} "
        f"chaos={chaos_summary.get('scenario_total', 0)} "
        f"dominant={analysis_summary['dominant_pattern']}"
    )


def run_pipeline(args: PipelineArgs) -> pc.PipelineState:
    """Run validated analysis and persist its paired artifacts."""
    run_id = _parse_run_id(args.run_id)
    output_dir = Path(args.output_dir)
    input_dir = Path(args.input_dir)
    run_dir = output_dir / "runs" / run_id
    input_run_dir = input_dir / run_id
    if os.path.lexists(run_dir) or os.path.lexists(input_run_dir):
        raise RunError(f"run id already exists: {run_id}")

    data = ai.load(args.input)
    config = ai.load_config(args.config)
    analysis = ai.analyze(data, playbook=config["patterns"])
    chaos = [] if args.skip_chaos else chaos_runner.run()
    chaos_summary: pc.ChaosSummary = {"status": "skipped"} if args.skip_chaos else _chaos_summary(chaos)
    analysis_summary = _analysis_summary(analysis)
    pattern = analysis_summary["dominant_pattern"]
    memory_path = output_dir / "_learnings.md"
    learned_context = (pm.select_context(memory_path, pattern=pattern, status="succeeded", recent=5)
                       if memory_path.exists() else "No prior matching lessons.")
    _reserve_run_dirs(input_run_dir, run_dir)
    _ = pm.ensure_memory(memory_path)

    artifacts: pc.ArtifactPaths = {
        "analysis": str(run_dir / "analysis.json"), "memory": str(memory_path),
        "chaos": None if args.skip_chaos else str(run_dir / "chaos.json"),
        "scenario_checklist": str(run_dir / "scenario-checklist.md"),
        "state": str(run_dir / "state.json"),
    }
    started_at = datetime.now(timezone.utc).isoformat()
    state = _state(run_id, args.input, args.config, artifacts, "running", started_at)
    _write_json(run_dir / "state.json", state)
    state["input_artifacts"] = _snapshot_inputs(args, input_run_dir)
    _write_json(run_dir / "state.json", state)

    _write_json(run_dir / "analysis.json", analysis)

    if not args.skip_chaos:
        _write_json(run_dir / "chaos.json", chaos)

    checklist = _render_checklist(data, analysis, chaos, learned_context)
    sf.write_text(run_dir / "scenario-checklist.md", checklist)

    state["status"] = "succeeded"
    state["finished_at"] = datetime.now(timezone.utc).isoformat()
    state["analysis_summary"] = analysis_summary
    state["chaos_summary"] = chaos_summary
    _write_json(run_dir / "state.json", state)
    learning = _success_memory_line(run_id, analysis_summary, chaos_summary)
    if not pm.append_learning(memory_path, "## §0 Run tracking", learning):
        print("pipeline succeeded; learning durability could not be confirmed", file=sys.stderr)
    return state


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MTS 안정성 반복학습 파이프라인 실행")
    _ = parser.add_argument("--input", default=ai.DEFAULT_INPUT, help="장애 이력 JSON 경로")
    _ = parser.add_argument("--config", default=ai.DEFAULT_CONFIG, help="분석·메모리 정책 JSON 경로")
    _ = parser.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), help="실행 식별자")
    _ = parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="실행 입력 스냅샷 루트")
    _ = parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="실행 산출물 루트")
    _ = parser.add_argument("--skip-chaos", action="store_true", help="카오스 재현 단계를 건너뛴다")
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    """Execute the pipeline CLI and return a process status."""
    parser = _parser()
    args = parser.parse_args(argv, namespace=PipelineArgs())
    try:
        run_id = _parse_run_id(args.run_id)
    except RunError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    output_dir = Path(args.output_dir)
    input_run_dir = Path(args.input_dir) / run_id
    run_dir = output_dir / "runs" / run_id

    def fail(message: str, code: int) -> int:
        if run_dir.exists():
            failed = _state(run_id, args.input, args.config, {}, "failed", datetime.now(timezone.utc).isoformat())
            failed["input_artifacts"] = _input_artifacts(input_run_dir) if input_run_dir.exists() else {}
            failed["finished_at"] = datetime.now(timezone.utc).isoformat()
            failed["error"] = message
            with contextlib.suppress(OSError):
                _write_json(run_dir / "state.json", failed)
        print(message, file=sys.stderr)
        return code

    previous_handler = signal.signal(signal.SIGALRM, _raise_timeout)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, PIPELINE_TIMEOUT_SECONDS)
    try:
        try:
            state = run_pipeline(args)
        except TimeoutError:
            return fail("pipeline execution timed out", 124)
        except (KeyboardInterrupt, GeneratorExit, SystemExit) as termination:
            interrupted = isinstance(termination, KeyboardInterrupt)
            if not pm.is_committed_termination(termination):
                _ = fail("pipeline execution interrupted" if interrupted else "pipeline execution terminated", 130 if interrupted else 1)
            raise
        except RunError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except (OSError, UnicodeError, json.JSONDecodeError, ai.AnalysisError, pm.MemoryEntryError):
            return fail("pipeline execution failed", 1)
    finally:
        _ = signal.setitimer(signal.ITIMER_REAL, 0.0)
        _ = signal.signal(signal.SIGALRM, previous_handler)
        _ = signal.setitimer(signal.ITIMER_REAL, *previous_timer)
    print(f"RUN_ID={state['run_id']}")
    print(f"STATE={run_dir / 'state.json'}")
    print(f"CHECKLIST={run_dir / 'scenario-checklist.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
