# Samil Independence Screening

AX 해커톤 예선 제출용 Codex 플러그인입니다. 삼일회계법인(Samil PwC)의
감사대상회사와 비감사용역 목록을 사용자가 제공하면, 데모용으로 구성 가능한
사용자 제공 JSON 룰셋에 따라 금지용역 여부를 1차 triage하는 업무를 돕습니다.

## 선택 문제

삼일회계법인은 회계감사 외에도 경영자문·세무 등 비감사 서비스를
수행합니다. 따라서 감사대상회사와 비감사용역 사이에서 독립성 훼손
위협이 발생하지 않는지 상시 점검해야 합니다.

이 제출물은 `docs/삼일회계법인/ulw-research-report-01.md.md`의
`#1 독립성 체커` 조치권장안을 채택합니다. 공개 자료만으로 삼일의 전체
내부 계약 포트폴리오를 입증할 수는 없으므로, "비감사 매출 규모"가 아니라
입력된 개별 용역이 룰셋상 `금지용역` 또는 `추가 검토 필요`에 해당하는지
판정하는 데 초점을 둡니다.

## 예선 5문항 답변

### 1. 무엇을, 누가, 어떤 상황에서 쓰나요?

삼일회계법인의 독립성·컴플라이언스 검토 담당자 또는 감사계약 검토자가
감사대상회사 목록과 비감사용역 후보 목록을 대조할 때 씁니다. 신규
비감사용역 제안, 기존 계약 점검, 제출용 데모처럼 CSV와 JSON 룰셋으로
검토 대상을 명확히 줄 수 있는 상황을 가정합니다.

### 2. 왜 이 문제를 선택했나요?

회계법인은 감사대상회사에 비감사용역을 제공할 때 독립성 훼손 위협을
점검해야 합니다. 연구 보고서는 삼일의 공개 사업보고서와 금융당국 자료를
근거로 이 문제가 공개·검증 가능한 제출 주제라고 판단했습니다. 다만 공개
자료만으로 내부 계약 전체를 확인할 수 없기 때문에, 제출물은 법적 결론이
아닌 금지용역 룰 판정 triage에 한정합니다.

### 3. 플러그인은 어떻게 작동하나요?

Codex skill은 역할과 작업 범위를 먼저 고정하고, 사용자에게 공개·합성·권한
있는 입력 파일인지 확인하게 한 뒤 아래 명령을 실행하도록 안내합니다.
반복 실행 흐름은 `samil_independence_run.py` wrapper가 담당하고, 기존 단일
실행 진입점은 `src/bin/independence_screen.py`입니다. 실행 코드는 감사대상회사와
비감사용역의 `client_id`를 대조한 뒤 사용자가 제공한 JSON 룰셋의
`prohibited_service_types`, `review_service_types`,
`network_service_keywords`에 맞춰 행별 위험도를 분류합니다.
wrapper는 실행별 `spec.md`, `context.md`, `report.md`, `review.md`,
`state.md`를 만들고, deterministic review가 통과한 경우에만 run id와
라벨·샘플 원문 대신 hash/redacted placeholder를 로컬 append-only memory에
남깁니다. 다음 실행은 실패 리뷰, 현재 룰과 맞는 라벨 hash, 최근 실행을
최대 20줄/8KiB 안에서 중복 제거해 context pack으로 참고합니다.
현재 구현 범위는 deterministic Codex skill과 CLI이며, `src/.mcp.json`은
빈 설정 파일입니다. MCP 서버, DART 수집, PDF 파싱, 웹 scraping은 구현하지
않았습니다.

### 4. AI를 어떻게 활용했나요?

AI는 공개 자료 기반 문제 후보를 비교하고, 입증 가능한 범위와 입증할 수
없는 내부 포트폴리오 주장을 분리하는 데 사용했습니다. 또한 Codex가 반복
실행할 수 있도록 role/task framing, context selection, review gate,
append-only learning, bounded loop, guardrail, README 답변을 정리하는 데
사용했습니다. 실행 중 학습은 제공 파일의 원문을 저장하지 않고 hash와
집계값을 다음 실행의 참고 데이터로 남기는 방식이며, wrapper 전용 옵션
중복처럼 애매한 입력은 실행 전에 거부합니다. 규칙 자체를 공식 법령
해석으로 확장하지 않습니다. 이 플러그인은 네트워크, DART, PDF scraping을
구현했다고 주장하지 않습니다.

### 5. 어떻게 검증했나요?

예시 CSV와 JSON 룰셋으로 CLI와 반복 실행 wrapper를 직접 실행해 Markdown
보고서와 실행 산출물이 생성되는지 확인합니다. 자동 검증은 pytest 54건으로
구성했고, 정상 Markdown 출력,
금지용역 우선순위, 비감사 고객 제외, 네트워크 키워드 대소문자 무시,
`client_id` 공백 정규화, Markdown 표 escape, 깨진 JSON, 빈 룰 값,
짧은 CSV 행, 초과 CSV 셀, 빈 필수 CSV 값, 잘못된 `--format`,
알 수 없는 CLI 옵션, 중복 CLI 옵션을 검증합니다. 리팩토링 검증으로는
중복 `--run-id` 거부, 누락된 `--output-dir` 값 거부, selected memory
중복 제거와 line budget, 중복·비ASCII 라벨 hash dedupe, 필수 리포트 섹션
누락 review 실패, backslash Markdown escape, 실행별 `input/`·`output/`
쌍 생성, `output/` 내 출력 산출물 분리, `state/memory` 분리를 추가했습니다.
예시 룰은
제출 데모를 위한 구성 파일이며 법률 자문이나
공식 규정 범위 전체의 자동 판정을 의미하지 않습니다. 제출 전에는
`src/.codex-plugin/plugin.json`,
`src/skills/samil-independence-screening/SKILL.md`, `.mcp.json`, 예시 파일,
`logs/` 구조가 예선 요구사항과 맞는지 확인하고, README가 5문항을 모두
답하는지 테스트 스크립트로 점검합니다. 최종 검증 명령은
`uv run pytest -q`, `uv run ruff check src tests`, `uv run basedpyright`이며
현재 모두 통과합니다.

## 구조

```text
삼일회계법인/
├── src/
│   ├── .codex-plugin/plugin.json
│   ├── .mcp.json
│   ├── bin/independence_screen.py
│   ├── bin/samil_independence_run.py
│   ├── config/samil-screening-config.json
│   ├── examples/
│   │   ├── audit_clients.csv
│   │   ├── independence_rules.json
│   │   └── non_audit_services.csv
│   ├── templates/
│   │   ├── review_TEMPLATE.md
│   │   ├── spec_TEMPLATE.md
│   │   └── state_TEMPLATE.md
│   └── skills/samil-independence-screening/SKILL.md
├── README.md
└── logs/
```

## 실행 예시

```bash
python3 src/bin/independence_screen.py \
  --audit-clients src/examples/audit_clients.csv \
  --non-audit-services src/examples/non_audit_services.csv \
  --rules src/examples/independence_rules.json \
  --format markdown
```

`--format`을 생략해도 기본값은 `markdown`입니다. 지원하지 않는 포맷이나
중복 CLI 옵션은 사용 오류로 거부하며, 필수 CSV 컬럼·셀 오류와 JSON 룰
형식 오류는 입력 오류로 보고합니다.

반복 실행과 로컬 학습 기록이 필요한 경우에는 wrapper를 사용합니다.

```bash
python3 src/bin/samil_independence_run.py \
  --audit-clients src/examples/audit_clients.csv \
  --non-audit-services src/examples/non_audit_services.csv \
  --rules src/examples/independence_rules.json \
  --run-id demo-learning \
  --input-dir input \
  --output-dir output \
  --memory-dir state/memory
```

이 명령은 `input/<run-id>/` 아래 Codex plugin 입력값과 실행 입력 맥락인
입력 CSV/JSON snapshot, `spec.md`, `context.md`, `state.md`를 만들고,
`output/<run-id>/` 아래에는 Codex plugin 출력 산출물인 `report.md`,
`review.md`만 저장합니다. 입력 검증 실패 시에도 같은 run id로
`input/<run-id>/state.md`와 `output/<run-id>/error.md`가 남아 실패 쌍을
확인할 수 있습니다. deterministic review가
통과한 경우에만 `state/memory/learning.md`에 redacted learning을 append합니다.
durable memory는 실행 단위 input/output 쌍이 아니므로 `input/`과 `output/`
밖에 둡니다. raw run id, raw rule label, raw client/service sample을
저장하지 않고 hash와 집계값만 남깁니다. 다음 실행은 이 memory에서 최대
20줄/8KiB만 selected memory로 참고할 수 있으며, 중복 라벨과 중복 memory
line은 제거됩니다.
중복 `--run-id` 또는 `--output-dir` wrapper 옵션은 애매한 실행으로 보고
오류 처리합니다.

## 검증 포인트

- `고위험`: 금지용역 룰셋에 포함된 서비스 유형입니다.
- `추가 검토 필요`: 사전 독립성 검토가 필요한 서비스 유형입니다.
- `낮음`: 현재 룰셋에서 금지 또는 검토 트리거가 확인되지 않았습니다.

이 결과는 독립성 검토를 위한 triage입니다. 최종 허용 여부나 법적 결론은
전문가 검토와 실제 계약·관계 자료 확인이 필요합니다.

## 로그

`logs/submission-evidence.jsonl`에는 공개 제출용으로 선별한 sanitized evidence
한 줄만 보관합니다. 원본 대화, private client data, raw 실행 로그는 이 저장소에
포함하지 않습니다.
