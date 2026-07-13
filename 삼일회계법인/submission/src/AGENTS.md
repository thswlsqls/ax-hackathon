# PLUGIN PACKAGE KNOWLEDGE BASE

## OVERVIEW

`src/` is the distributable Codex plugin boundary: metadata, one screening skill, executable Python, synthetic examples, and tested contract assets.

## STRUCTURE

```text
src/
├── .codex-plugin/plugin.json  # Plugin identity and skill discovery
├── .mcp.json                  # Intentionally empty; no MCP implementation
├── bin/                       # Runtime implementation; see child AGENTS.md
├── skills/                    # Agent-facing workflow and domain guardrails
├── config/                    # Submission contract configuration
├── examples/                  # Synthetic audit/service/rule inputs
└── templates/                 # Expected artifact shapes
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Plugin name, version, capability metadata | `.codex-plugin/plugin.json` | `skills` must remain `./skills/` |
| Screening workflow and safety language | `skills/samil-independence-screening/SKILL.md` | Source of truth for agent behavior |
| Executable implementation | `bin/` | Child instructions define runtime seams |
| Storage/redaction contract values | `config/samil-screening-config.json` | Tests read it; production Python does not |
| Demonstration inputs | `examples/` | Synthetic fixtures used by README and tests |
| Spec/review/state document shapes | `templates/` | Contract assets; production renders inline |

## CONVENTIONS

- Keep plugin metadata, README claims, skill wording, config, examples, and contract tests aligned; these surfaces jointly define the submission.
- Preserve Python 3.9 compatibility and strict typing. Do not use syntax or standard-library APIs introduced after 3.9.
- Maintain exact CSV headers and JSON arrays documented in `SKILL.md`; loaders reject missing, extra, short, or blank required values.
- Keep examples synthetic and safe to distribute. Never replace them with private client data.
- State capabilities precisely: `.mcp.json` is empty, and DART, PDF, web scraping, and external collection are not implemented.

## ANTI-PATTERNS

- Do not treat config or templates as live runtime inputs without changing production code and tests together.
- Do not broaden the skill from supplied-rule triage into legal interpretation or final independence approval.
- Do not add outside facts or inferred contracts to reports; missing information remains explicitly missing.
- Do not add another `AGENTS.md` inside the single skill; its `SKILL.md` already provides the local workflow.

## VERIFICATION

```bash
uv run ruff check src tests
uv run basedpyright
uv run pytest -q tests/test_submission_contract.py
```
