# 계약서 리스크 점검 리포트

> 본 리포트는 법률 자문이 아니다. 계약 검토 우선순위를 정하기 위한 사전 점검 결과입니다.

## Schema
| Field | Required | Description |
|---|---:|---|
| target | yes | Input description or local path. |
| summary | yes | Finding counts by risk. |
| findings | yes | Risk candidates sorted by risk. |
| next_steps | yes | Human review queue, not final legal judgment. |

## Findings
| priority | risk | clause | issue | legal_basis_candidate | suggested_rewrite | confidence |
|---:|---|---|---|---|---|---|
| `1` | `<상|중|하>` | `<clause>` | `<risk candidate>` | `<law candidate>` | `<draft>` | `<높음|중간|낮음>` |

## Human Review Queue
- `<legal/compliance reviewer action>`
