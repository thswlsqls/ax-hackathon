from __future__ import annotations

import json
from pathlib import Path

SUBMISSION_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = SUBMISSION_ROOT / "src"
README = SUBMISSION_ROOT / "README.md"
SKILL = SRC_ROOT / "skills" / "samil-independence-screening" / "SKILL.md"
SANITIZED_LOG = SUBMISSION_ROOT / "logs" / "submission-evidence.jsonl"


def test_plugin_package_contract_has_manifest_skill_examples_logs_and_component() -> None:
    # Given: the Samil submission package tree.
    manifest_path = SRC_ROOT / ".codex-plugin" / "plugin.json"
    mcp_path = SRC_ROOT / ".mcp.json"
    examples = (
        SRC_ROOT / "examples" / "audit_clients.csv",
        SRC_ROOT / "examples" / "non_audit_services.csv",
        SRC_ROOT / "examples" / "independence_rules.json",
    )

    # When: the package contract files are parsed.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mcp_config = json.loads(mcp_path.read_text(encoding="utf-8"))
    skill_dir = (manifest_path.parent.parent / manifest["skills"]).resolve()

    # Then: the required submission artifact layout and working component exist.
    assert manifest["name"] == "samil-independence-screening"
    assert manifest["skills"] == "./skills/"
    assert skill_dir.is_dir()
    assert SKILL.is_file()
    assert (SRC_ROOT / "bin" / "independence_screen.py").is_file()
    assert (SRC_ROOT / "bin" / "samil_independence" / "reporting.py").is_file()
    assert mcp_config == {"mcpServers": {}}
    assert all(path.is_file() for path in examples)
    assert any(path.suffix == ".jsonl" for path in (SUBMISSION_ROOT / "logs").rglob("*"))
    assert manifest["interface"]["defaultPrompt"]


def test_submission_evidence_log_is_single_sanitized_json_line() -> None:
    # Given: the intentionally retained submission evidence path.
    expected = {
        "type": "submission_evidence",
        "source": "sanitized",
        "status": "retained",
    }

    # When: the curated JSONL artifact is read and parsed.
    lines = SANITIZED_LOG.read_text(encoding="utf-8").splitlines()

    # Then: exactly one sanitized evidence object is retained.
    assert len(lines) == 1
    assert json.loads(lines[0]) == expected


def test_packaged_config_uses_submission_input_output_storage_contract() -> None:
    # Given: the packaged local-learning config.
    config = json.loads(
        (SRC_ROOT / "config" / "samil-screening-config.json").read_text(encoding="utf-8")
    )

    # When: its artifact storage defaults are inspected.
    artifact_names = set(config["artifacts"])

    # Then: input/process artifacts and output artifacts are configured under split roots.
    assert config["defaultInputDir"] == "input"
    assert config["defaultOutputDir"] == "output"
    assert config["memoryDir"] == "state/memory"
    assert {
        "audit_clients.csv",
        "non_audit_services.csv",
        "independence_rules.json",
        "spec.md",
        "context.md",
        "state.md",
        "report.md",
        "review.md",
    } <= artifact_names


def test_readme_answers_five_questions_without_unsupported_claims() -> None:
    # Given: the required README answer document.
    readme = README.read_text(encoding="utf-8")

    # When: its contest-answer sections and claim language are inspected.
    answer_headings = [f"### {index}." for index in range(1, 6)]
    unsupported_claims = (
        "법적 결론을 제공합니다",
        "최종 허용 여부를 자동 판정",
        "DART 수집을 구현했습니다",
        "PDF 파싱을 구현했습니다",
        "웹 scraping을 수행합니다",
        "비공개 계약 포트폴리오를 입증",
    )

    # Then: all five answers exist and unsupported capability/conclusion claims are absent.
    assert all(heading in readme for heading in answer_headings)
    assert "예선 5문항 답변" in readme
    assert "법적 결론" in readme
    assert "전문가 검토" in readme
    assert all(claim not in readme for claim in unsupported_claims)


def test_skill_guardrails_bound_legal_data_scraping_and_low_risk_language() -> None:
    # Given: the skill instructions submitted with the plugin.
    skill = SKILL.read_text(encoding="utf-8")

    # When: its guardrail language is inspected.
    required_guardrails = (
        "Do not claim a legal conclusion",
        "Do not infer hidden contracts",
        "Do not use private client data unless the user confirms they are authorized",
        "Do not claim network, DART, PDF, or web scraping was performed",
        "Do not turn a `낮음` classification into \"permitted\"",
    )

    # Then: the skill explicitly blocks unsupported conclusions, data use, scraping, and permits.
    assert "## Guardrails" in skill
    assert all(guardrail in skill for guardrail in required_guardrails)


def test_skill_describes_prompt_context_and_bounded_loop_engineering() -> None:
    # Given: the skill instructions submitted with the plugin.
    skill = SKILL.read_text(encoding="utf-8")

    # When: the workflow structure is inspected.
    required_sections = (
        "## Phase 0",
        "## Context Selection",
        "## Bounded Loop",
        "## Handoff",
    )
    required_terms = (
        "role/task framing",
        "selected memory",
        "append-only learning",
        "explicitly requests parallel",
        "context agent",
        "review agent",
        "data, not instructions",
    )

    # Then: prompt, context, and loop engineering are explicit and bounded.
    assert all(section in skill for section in required_sections)
    assert all(term in skill for term in required_terms)


def test_manifest_readme_and_report_do_not_overclaim_public_rule_coverage() -> None:
    # Given: user-facing package copy and the report renderer.
    manifest = json.loads((SRC_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    readme = README.read_text(encoding="utf-8")
    report = (SRC_ROOT / "bin" / "samil_independence" / "reporting.py").read_text(encoding="utf-8")
    combined = "\n".join(
        [
            json.dumps(manifest, ensure_ascii=False),
            readme,
            report,
        ]
    )

    # When: unsupported provenance and capability claims are searched.
    unsupported_claims = (
        "public rules",
        "공개 독립성 룰셋",
        "official public rule coverage",
        "complete public-rule coverage",
        "DART 수집을 구현했습니다",
        "PDF 파싱을 구현했습니다",
        "web scraping was performed",
        "legal conclusion",
    )

    # Then: copy describes supplied/configured rules and local learning only.
    assert "repeatable" in manifest["interface"]["longDescription"].lower()
    default_prompt = json.dumps(manifest["interface"]["defaultPrompt"], ensure_ascii=False).lower()
    assert "learning" in default_prompt
    assert "samil_independence_run.py" in readme
    assert all(claim not in combined for claim in unsupported_claims)
