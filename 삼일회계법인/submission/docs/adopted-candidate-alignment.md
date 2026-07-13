# 채택 후보 및 구현 정합성 확인

## 채택 후보

제출물은 `docs/삼일회계법인` 아래 연구 문서의 최종 권고 중 **감사인 독립성·비감사용역 충돌 자동 스크리닝**을 채택했다.

- `deep-research-report-01.md`는 최종 1순위 후보를 **감사인 독립성·비감사용역 충돌 자동 스크리닝**으로 정리했다. 근거는 삼일의 자문·비감사용역 구조가 감사 독립성 리스크와 직접 연결되고, 감사 고객·비감사용역·금지용역 룰셋 대조가 결정론적 컴플라이언스 자동화에 적합하다는 점이다.
- `ulw-research-report-01.md.md`는 `#1 독립성 체커`를 **조치권장안 채택(ADOPTED, 2026-07-08)**으로 표시했다. 단, 원래의 “규모 스크리닝” 프레이밍은 과장 가능성이 있어 **금지용역 룰 판정**으로 초점을 좁히라고 권고했다.

따라서 제출 구현의 기준 후보는 “삼일의 감사 고객과 비감사용역 후보를 대조해 금지용역 또는 추가 검토 필요 항목을 1차 분류하는 독립성 스크리닝 플러그인”이다.

## 구현 반영 범위

현재 제출물은 채택 후보를 다음 범위로 구현한다.

- `src/.codex-plugin/plugin.json`: `samil-independence-screening` 플러그인 메타데이터와 skill 경로를 정의한다.
- `src/skills/samil-independence-screening/SKILL.md`: 사용자가 제공한 감사 고객 CSV, 비감사용역 CSV, 독립성 룰 JSON을 기준으로 Codex가 스크리닝을 수행하도록 안내한다.
- `src/bin/independence_screen.py`: `client_id`로 감사 고객과 비감사용역을 매칭하고, `prohibited_service_types`, `review_service_types`, `network_service_keywords` 룰을 적용한다.
- `src/bin/samil_independence_run.py`: 반복 실행 단위로 입력값과 출력 산출물을 분리 저장한다. 입력 snapshot, `spec.md`, `context.md`, `state.md`는 `input/<run-id>/`에, `report.md`, `review.md`, 실패 `error.md`는 `output/<run-id>/`에 저장한다.
- `src/bin/samil_independence/reporting.py`: 위험도 요약과 행별 사유를 Markdown 리포트로 출력한다.
- `src/config/samil-screening-config.json`: 기본 실행 루트를 `input`, `output`, `state/memory`로 정의해 durable memory가 실행별 input/output 쌍을 오염시키지 않게 한다.
- `src/examples/`: 합성 감사 고객, 비감사용역, 룰셋 예시를 제공해 공개·데모 데이터만으로 실행을 재현할 수 있게 한다.
- `tests/`: 정상 예시 실행, 분류 우선순위, Markdown escape, 제출 패키지 구조, malformed CSV/JSON, CLI 옵션 오류, 실행별 `input/`·`output/` 쌍과 `state/memory` 분리를 검증한다.

위 구현은 채택안의 핵심인 “감사 고객 × 비감사용역 × 금지/검토 룰셋 교차검증”에 해당한다.

## 구현에서 제외한 범위

연구 문서에는 더 넓은 확장 아이디어도 포함되어 있으나, 현재 제출물은 예선 제출 안정성과 공개 데이터 한계를 고려해 아래 범위를 구현하지 않는다.

- DART, 웹, PDF, HTML에서 계약·금액·공시를 자동 수집하지 않는다.
- 삼일의 실제 내부 계약 포트폴리오나 승인 이력을 입증하지 않는다.
- 외부감사법·독립성 규정 전체를 법률적으로 해석하거나 최종 허용 여부를 판단하지 않는다.
- `낮음`을 “허용”으로 표현하지 않고, supplied rule trigger가 확인되지 않았다는 의미로만 사용한다.
- 품질관리 감리 self-QA, 지정감사 readiness, 감사절차 자동화는 보조 또는 대안 후보로 남기고 이번 제출 구현에는 포함하지 않는다.

이 제외 범위는 `README.md`와 `SKILL.md`의 guardrail과 일치한다.

## 정합성 판정

| 항목 | 연구 채택안 | 제출 구현 | 정합성 |
|---|---|---|---|
| 문제 초점 | 독립성 충돌·금지용역 룰 판정 | 감사 고객과 비감사용역 후보를 룰셋으로 분류 | 일치 |
| 입력 | 감사 고객, 비감사용역, 금지/검토 룰 | CSV 2개와 JSON 룰셋 | 일치 |
| 산출물 | 위험 등급 리포트, 추가 확인 대상 | Markdown 요약·상세·추가 검토 안내 | 일치 |
| 실행 저장 계약 | 실행별 입력과 출력 근거 확인 가능 | `input/<run-id>/`에는 입력 snapshot과 process state, `output/<run-id>/`에는 `report.md`·`review.md` 또는 `error.md`만 저장 | 일치 |
| durable memory | 다음 실행 참고 가능하되 원문 저장 금지 | `state/memory/learning.md`에 hash·집계값만 저장하고 `input/`·`output/` 쌍에서는 제외 | 일치 |
| 입력 오류 처리 | 제공 파일 기반의 재현 가능한 검토 | 누락 컬럼, 짧은 행, 초과 셀, 빈 필수 값, 깨진 JSON, 알 수 없는/중복 CLI 옵션 거부 | 일치 |
| 데이터 범위 | 공개/샘플 데이터 기반 데모 권장 | 예시 CSV/JSON 제공, 내부 포트폴리오 미주장 | 일치 |
| 법적 결론 | 최종 판단 아님 | triage와 전문가 검토 필요 명시 | 일치 |
| 확장 수집 | 원안 일부에서 DART/PDF/웹 가능성 언급 | 미구현으로 명시 | 의도적 축소 |

## 검증 결과

구현 기준으로 문서 정합성을 다시 확인했다.

- `uv run pytest -q`: 54 passed.
- `uv run ruff check src tests`: All checks passed.
- `uv run basedpyright`: 0 errors, 0 warnings, 0 notes.
- 수동 wrapper QA: `input/qa-storage/`에는 입력 snapshot, `spec.md`, `context.md`, `state.md`가 있고, `output/qa-storage/`에는 `report.md`, `review.md`만 있다.
- 실패 실행 QA: `input/pytest-failure/`와 `output/pytest-failure/error.md`가 같은 run id로 남는다.
- `input/memory`는 없고, durable memory는 `state/memory/learning.md`에만 있다.

종합하면, 제출물은 연구 문서의 채택 후보를 그대로 과장해 구현한 것이 아니라, 최종 권고의 핵심인 **금지용역 룰 판정 중심 독립성 스크리닝**으로 범위를 좁혀 구현했다. 이 범위는 README, skill guardrail, CLI 동작, 예시 데이터, 실행별 artifact 저장 계약, 테스트 검증과 정합적이다.
