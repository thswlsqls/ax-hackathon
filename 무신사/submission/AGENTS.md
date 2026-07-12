# PROJECT KNOWLEDGE BASE

**Generated:** 2026-07-10 14:43 JST  
**Commit:** unavailable (not a Git worktree)  
**Branch:** unavailable (not a Git worktree)

## OVERVIEW

Hackathon submission for a Codex plugin that flags Korean retail-contract risk clauses. The product combines a deterministic, standard-library Python scanner with bounded role prompts, policy JSON, artifact templates, and append-only run learning; it produces a review queue, not a final legal judgment.

## STRUCTURE

```text
submission/
├── src/                                      # Authored plugin; actual product root
│   ├── .codex-plugin/plugin.json             # Plugin discovery manifest
│   └── skills/contract-risk-scanner/         # Self-contained skill domain
├── docs/                                     # Research basis and submission narrative
├── input/<run-id>--input.md                   # Persisted execution input records
├── output/<run-id>--{baseline.json,review.md,report.md,state.md}                          # Persisted execution artifacts
├── output/_learnings.md                      # Append-only cross-run memory
└── logs/                                     # Conversation-log submission guidance; no session logs committed
```

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Understand user-facing behavior | `src/skills/contract-risk-scanner/SKILL.md` | Orchestrates scan, bounded review roles, report, validation, and learning |
| Change plugin metadata | `src/.codex-plugin/plugin.json` | Skills root is `./skills/` |
| Change privacy or report policy | `src/skills/contract-risk-scanner/config/musinsa-config.json` | Policy source of truth |
| Change clause detection | `src/skills/contract-risk-scanner/rules/clause_rules.json` | Seven data-driven rules; prefer this over hard-coding |
| Change executable behavior | `src/skills/contract-risk-scanner/scripts/` | Six Python modules: four direct entry/validation scripts, one edge suite, and one renderer |
| Change artifact rendering | `src/skills/contract-risk-scanner/scripts/render_review_artifacts.py` | Artifact models, baseline sanitization, and deterministic text rendering |
| Change role boundaries | `src/skills/contract-risk-scanner/roles/` | Four allowed-input/output contracts |
| Change artifact schema | `src/skills/contract-risk-scanner/templates/` | Input, review, report, state, and learning shapes |
| Check expected behavior | `src/skills/contract-risk-scanner/fixtures/EXPECTED.md` | Includes intentional contextual false positives |
| Review problem evidence | `docs/deep-research-report-01.md` | Public-source research behind the submission |

## CODE MAP

| Symbol | Type | Location | Refs | Role |
|---|---|---|---:|---|
| `scan` | function | `scripts/scan_contract.py` | 4 | Splits clauses and applies keyword rules |
| `write_run` | function | `scripts/run_contract_review.py` | 1 | Owns secure paired run creation and artifact writes |
| `RunRequest` | class | `scripts/render_review_artifacts.py` | 7 | Shared typed run and rendering boundary |
| `validate_all` | function | `scripts/validate_pipeline.py` | 1 | Fans out across config, roles, artifacts, privacy, and source policy |
| `assert_true` | function | `scripts/validate_pipeline.py` | 11 | Central validator assertion helper |
| `run_scan` | function | `scripts/verify_fixtures.py` | 3 | Drives scanner CLI regression scenarios |

All paths in the code map are relative to `src/skills/contract-risk-scanner/`. `Refs` is the indexed structural in-degree (edge count), not a count of distinct symbols or call expressions.

## CONVENTIONS

- Python 3.9+ and standard library only; there is no package manager, build metadata, formatter, or CI workflow.
- The skill directory is the reliable working directory. Executables are invoked directly as `python3 scripts/<name>.py`.
- Config, rules, role prompts, templates, and fixtures are first-class runtime contracts, not supporting prose.
- Runtime state lives outside plugin source. Each run pairs `input/<run-id>--input.md` with four files under `output/<run-id>--{baseline.json,review.md,report.md,state.md}`.
- Regression coverage is CLI/subprocess-oriented: exact exit codes, messages, artifact layout, privacy, and persistence are part of behavior.

## ANTI-PATTERNS (THIS PROJECT)

- Never edit, excerpt, censor, or delete `logs/**`; they are verbatim submission evidence. Keep secrets out of prompts and logs. If sensitive content is captured, stop distribution, rotate affected credentials, restrict access, and escalate to the owner/organizer before evidence-preserving remediation.
- Never hand-edit persisted run artifacts as source or reuse an existing run ID. Preserve input/output pairing.
- Never replace `output/_learnings.md`; reread it before appending one execution row.
- Never present scanner matches as confirmed illegality or legal advice. Preserve risk-candidate wording and the legal disclaimer.
- Never treat “no keyword match” as “no risk”; contextual adjudication and human review remain required.
- Treat `input/**`, raw `baseline.json`, and learning memory as confidential contract data; do not paste, publish, or attach them outside the requested review flow.

## COMMANDS

Run from `src/skills/contract-risk-scanner`:

```bash
python3 scripts/scan_contract.py fixtures/sample_contract_01.md --format md
PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify_fixtures.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_pipeline_edges.py
python3 scripts/validate_pipeline.py --skill-dir . --input-dir ../../../input --output-dir ../../../output
```

Expected markers: `fixture verification passed: 13 scenarios`, 22 successful edge tests, and `pipeline validation passed`.

## NOTES

- `validate_pipeline.py` is stateful when pointed at the retained root directories: it creates a unique QA run and appends learning memory. Use temporary input/output directories for disposable validation.
- `sample_contract_02.md` deliberately yields three medium baseline matches; contextual review is expected to exclude them from final findings.
- No LSP server for Python is installed in this environment; the code map comes from the indexed knowledge graph and executable regression surfaces.
