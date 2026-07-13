# EXECUTABLE CORE KNOWLEDGE BASE

## OVERVIEW

`src/bin/` is one cohesive executable boundary shared by the one-shot CLI and the stateful wrapper; imports assume this directory is on `sys.path`.

## WHERE TO LOOK

| Concern | Location | Contract |
|---|---|---|
| Domain records, CSV/JSON loading, classification, CLI parsing | `independence_screen.py` | Stateless stdout Markdown; input errors return 2 |
| Stateful orchestration | `samil_independence_run.py` | Snapshot before validation; review before learning |
| Markdown rendering and escaping | `samil_independence/reporting.py` | Shared by both entrypoints |
| Run paths, state/review text, memory | `samil_independence/runtime.py` | Paired artifacts and hash/redaction rules |

## CALL FLOW

```text
direct main -> parse/load -> screen -> classify_service -> render_markdown
wrapper main -> prepare/snapshot -> parse/load -> select memory -> screen
             -> render_markdown -> review_report -> write artifacts -> append_learning
```

## CONVENTIONS

- Keep business priority exact: prohibited service type wins over review type; review type wins over description keyword; otherwise return `낮음`.
- `reporting.py` depends on the `FindingRow` protocol. Preserve that structural boundary instead of importing concrete screening models.
- Keep `input/<run-id>` for snapshots/spec/context/state, `output/<run-id>` for report/review or error, and `state/memory/learning.md` for durable learning.
- Append learning only after deterministic review passes. Persist hashes, counts, and `[redacted]`, never raw client/service/fee/prompt data.
- Context selection remains deduplicated and bounded to 20 lines and 8192 bytes, prioritized by failed/pending review, matching rule-label hashes, then recency.
- Use a fresh safe run ID for manual QA. Existing run directories are not cleared, so reuse can leave stale files.

## ANTI-PATTERNS

- Do not add more responsibilities to `independence_screen.py`; it already combines domain models, parsing, classification, and CLI behavior.
- Do not change Markdown headings or introduce forbidden conclusion wording without updating `review_report` and report tests together.
- Do not use unrestricted directory options with untrusted values; only the run-ID component is path-validated.
- Do not manually append to memory or concurrently run wrappers against the same memory file; appends are not locked.
- Do not introduce a nested guide under `samil_independence/`; reporting and runtime share this parent contract.

## VERIFICATION

```bash
uv run pytest -q tests/test_independence_screen_cli.py tests/test_markdown_report_cli.py
uv run pytest -q tests/test_learning_runtime.py tests/test_learning_wrapper.py tests/test_learning_wrapper_args.py
uv run ruff check src tests
uv run basedpyright
python3 src/bin/independence_screen.py --help
```
