# Run State

## Schema
| Field | Required | Description |
|---|---:|---|
| run_id | yes | Stable run identifier. |
| current_status | yes | Latest status. |
| input_path | yes | Paired path to `input/<run-id>--input.md`. |
| baseline_path | yes | Path to `<run-id>--baseline.json`. |
| review_path | yes | Path to `<run-id>--review.md`. |
| report_path | yes | Path to `<run-id>--report.md`. |
| validation_result | yes | `pending`, `passed`, or `failed`. |
| history | yes | Append-only status table. |

## Status
- run_id: `<run-id>`
- current_status: `reported`
- input_path: `input/<run-id>--input.md`
- baseline_path: `<run-id>--baseline.json`
- review_path: `<run-id>--review.md`
- report_path: `<run-id>--report.md`
- validation_result: `pending`

## Append-Only History
| status | artifact | note |
|---|---|---|
| created | input/<run-id>--input.md | input normalized |
| scanned | <run-id>--baseline.json | scanner baseline created |
| reviewed | <run-id>--review.md | role review draft created |
| reported | <run-id>--report.md | report draft created |
