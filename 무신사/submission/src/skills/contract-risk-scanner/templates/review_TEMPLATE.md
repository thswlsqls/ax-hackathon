# Review Draft

> 본 초안은 법률 자문이 아니다. 결정론적 baseline 후보를 사람이 검토하기 쉽도록 재정리한 것이다.

## Schema
| Field | Required | Description |
|---|---:|---|
| baseline_path | yes | Path to `output/<run-id>--baseline.json`. |
| learning_context | yes | Injected lessons used in this run, or `none`. |
| decisions | yes | One row per finding. |

## Decisions
| rule_id | clause | baseline_risk | confidence | decision | reason | rewrite_candidate |
|---|---|---|---|---|---|---|
| `<rule>` | `<clause>` | `<상|중|하>` | `<높음|중간|낮음>` | `<keep|lower|exclude|needs-human-review>` | `<short reason>` | `<candidate>` |
