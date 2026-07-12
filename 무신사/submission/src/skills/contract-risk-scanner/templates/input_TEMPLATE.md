# Input Record

## Schema
| Field | Required | Description |
|---|---:|---|
| run_id | yes | Stable run identifier under `input/<run-id>--input.md`, paired with `output/<run-id>--{baseline.json,review.md,report.md,state.md}`. |
| source_kind | yes | `demo_fixture`, `local_file`, or `explicit_user_paste`. |
| source_path | yes | Local path or `chat-paste`; never a remote URL. |
| privacy_mode | yes | Defaults to `local_only`. |
| redaction_summary | yes | What was withheld from role prompts. |
| scanner_input | yes | Local file path used by `scan_contract.py`. |

## Record
- run_id: `<run-id>`
- source_kind: `<demo_fixture|local_file|explicit_user_paste>`
- source_path: `<local path>`
- privacy_mode: `local_only`
- redaction_summary: `<summary>`
- scanner_input: `<local path>`
- output_artifact_set: `output/<run-id>--{baseline.json,review.md,report.md,state.md}`
