# 예선 5문항 요약

## 무엇을, 누가, 어떤 상황에서 쓰나요? (최대 800자)

삼일회계법인의 독립성·컴플라이언스 담당자, 감사계약 검토자, 또는 비감사용역 제안서를 1차로 점검하는 실무자가 쓰는 Codex 플러그인입니다. 사용자는 감사대상회사 목록 CSV, 검토할 비감사용역 후보 CSV, 사내 또는 데모용 독립성 룰 JSON을 준비한 뒤 Codex에 스크리닝을 요청합니다. 신규 자문 계약 제안이 들어왔을 때, 기존 계약 목록을 정기 점검할 때, 또는 해커톤 제출처럼 합성 예시 데이터로 동작을 재현해야 할 때를 가정했습니다. 이 도구는 계약 승인 여부를 대신 결정하지 않고, 감사 고객과 비감사용역 후보를 `client_id`로 대조해 금지용역, 추가 검토 필요, 낮음 항목을 분류하는 triage 도구입니다. 따라서 법률 자문이나 최종 독립성 판단이 아니라, 담당자가 어떤 계약을 먼저 확인해야 하는지 좁히는 데 쓰입니다. 출력 리포트는 위험도별 건수와 행별 사유를 보여 주므로 검토 회의 전 사전 목록 정리, 추가 자료 요청, 승인 이력 확인 대상 선별에 활용할 수 있습니다. 특히 여러 후보 용역을 한 번에 검토할 때 반복적인 대조 작업을 줄이고, 사람이 놓칠 수 있는 금지용역 키워드와 네트워크 관련 설명을 빠르게 표시하는 역할을 합니다. 실무자는 이 결과를 검토 메모의 초안으로 사용할 수 있습니다. 입력 파일에 없는 고객·계약은 평가하지 않으며, 민감한 내부 자료는 사용자가 권한을 가진 경우에만 넣는다는 전제를 둡니다.

## 왜 이 문제를 선택했나요? (최대 800자)

이 문제를 선택한 이유는 회계법인의 비감사용역이 감사 독립성과 직접 연결되는 공개·검증 가능한 업무 리스크이기 때문입니다. 삼일회계법인은 감사 외에도 세무·경영자문 등 다양한 전문서비스를 제공하므로, 감사대상회사에 어떤 비감사용역을 제공하는지 점검하는 절차가 중요합니다. 공개 연구 과정에서는 삼일 사업보고서 제55기의 「3. 사업부문별 매출액」 부속명세서(PDF 30~31쪽, 감사대상회사 경영자문 매출 144억9,390만원은 31쪽)와 금융당국 자료를 통해 회계법인이 감사대상회사 비감사업무 수임 시 독립성 훼손이 발생하지 않도록 점검해야 한다는 문제의식을 확인했습니다. 다만 공개 자료만으로 삼일의 실제 내부 계약 전체나 개별 승인 이력을 알 수는 없습니다. 그래서 “비감사 매출 규모를 자동 분석한다”거나 “법적 허용 여부를 판정한다”는 식의 과장된 범위는 제외했습니다. 대신 사용자가 제공한 CSV와 JSON 룰셋 안에서 개별 용역 유형이 금지 또는 추가 검토 대상인지 판정하는 좁고 재현 가능한 문제로 정의했습니다. 이 방식은 비공개 계약 원장을 요구하지 않아 예시 데이터로 검증 가능하고, 실제 업무에서도 담당자가 이미 가진 목록을 빠르게 1차 분류하는 데 도움이 됩니다. 또한 Codex 플러그인의 장점인 반복 실행, 입력 검증, 보고서 초안 생성을 보여 주기에 적합했습니다. 심사자가 실행 결과를 직접 확인하기도 쉽습니다. 그래서 제출물의 효과를 과장하지 않고도 문제 해결성을 설명할 수 있습니다. 공개 근거, 실제 업무성, 플러그인 실행 가능성을 동시에 만족한다고 판단했습니다.

**공식 출처**

- 삼일회계법인 사업보고서 제55기(2025.6.30, PwC코리아 공식 공시), 「3. 사업부문별 매출액」 부속명세서 PDF 30~31쪽: 총매출 1조1,093억6,638만원 중 회계감사 34.79%·세무 24.86%·경영자문 40.34%로 자문 비중이 감사를 앞섰고(30~31쪽), 감사대상회사에 대한 경영자문 매출 144억9,390만원(총매출의 1.31%)을 31쪽에 별도 공시했다. https://www.pwc.com/kr/ko/aboutus/samilpwc_business-report_55th.pdf
- 금융감독원 「2024사업연도 회계법인 사업보고서 분석 결과」(2025.11.25): 회계법인이 감사대상회사에 비감사업무를 수임할 때 독립성 훼손이 발생하지 않도록 철저히 점검할 필요가 있다고 밝혔다. https://eiec.kdi.re.kr/policy/materialView.do?num=273797

## 플러그인은 어떻게 작동하나요? (최대 800자)

플러그인은 Codex skill과 Python CLI로 구성됩니다. `src/.codex-plugin/plugin.json`은 플러그인 메타데이터와 skill 경로를 제공하고, `src/skills/samil-independence-screening/SKILL.md`는 Codex가 사용자에게 입력 권한과 룰 출처를 확인하도록 안내합니다. 단일 판정은 `src/bin/independence_screen.py`가 수행합니다. CLI는 감사 고객 CSV와 비감사용역 CSV의 `client_id`를 대조하고, JSON 룰의 `prohibited_service_types`, `review_service_types`, `network_service_keywords`를 적용합니다. 금지용역은 `고위험`, 검토 대상 유형이나 네트워크 키워드가 있으면 `추가 검토 필요`, 나머지는 `낮음`으로 분류합니다. 반복 실행은 `src/bin/samil_independence_run.py` wrapper가 담당합니다. wrapper는 실행별 입력 snapshot, `spec.md`, `context.md`, `state.md`를 `input/<run-id>/`에 저장하고, 출력 산출물인 `report.md`, `review.md` 또는 실패 `error.md`만 `output/<run-id>/`에 저장합니다. review 통과 시 durable memory는 실행 쌍 밖의 `state/memory/learning.md`에 hash와 집계값으로만 저장합니다. MCP 서버, DART 수집, PDF 파싱, 웹 scraping은 구현하지 않았고, 제공된 파일과 룰셋만 사용합니다.

## AI를 어떻게 활용했나요? (최대 800자)

AI는 문제 후보를 좁히고 제출 범위를 현실적으로 정하는 데 사용했습니다. 처음에는 삼일회계법인과 회계감사 산업에서 공개 자료로 입증 가능한 문제들을 비교했고, 그중 Codex 플러그인으로 반복 실행할 수 있는 독립성 스크리닝을 선택했습니다. 이후 AI를 활용해 “공개 자료로 말할 수 있는 사실”과 “내부 계약 데이터가 없으면 단정할 수 없는 주장”을 분리했습니다. 구현 단계에서는 role/task framing, 입력을 instruction이 아닌 data로 다루는 guardrail, selected memory, review gate, append-only learning, bounded loop를 skill과 wrapper에 반영했습니다. 학습 메모리는 원문 저장이 아니라 hash와 집계값 저장으로 제한했고, 중복 wrapper 옵션처럼 애매한 입력은 실행 전에 거부하도록 개선했습니다. 또한 `낮음`을 “허용”으로 표현하지 말 것, DART·PDF·웹 scraping을 수행했다고 주장하지 말 것, 사용자 입력이 공개·합성·권한 있는 자료인지 확인할 것 같은 제약을 문서와 테스트에 반영했습니다. AI가 만든 구현 주장은 직접 실행 가능한 CLI, pytest, ruff, basedpyright, 수동 wrapper QA로 다시 확인했습니다. 최종 산출물은 AI 초안을 사람이 검토해 범위와 표현을 조정한 결과입니다.

## 어떻게 검증했나요? (최대 800자)

예시 데이터로 CLI와 wrapper를 직접 실행해 리포트 제목, `고위험: 1건`, `추가 검토 필요: 2건`, 전문가 검토 필요 문구, 실행별 `input/<run-id>/`와 `output/<run-id>/` 쌍, redacted memory 생성을 확인했습니다. 성공 실행은 입력 snapshot·`spec.md`·`context.md`·`state.md`를 `input/`에, `report.md`·`review.md`만 `output/`에 남기고, 입력 실패 실행은 `input/<run-id>/state.md`와 `output/<run-id>/error.md`를 남깁니다. durable memory는 `input/`·`output/` 밖의 `state/memory/learning.md`에 저장됩니다. 자동 검증은 pytest 54건입니다. 기존 분류 로직, 입력 오류, Markdown escape, 제출 패키지 구조, README/skill guardrail 외에 중복 `--run-id`, 누락된 `--output-dir`, 중복 `--input-dir`, selected memory, 라벨 hash dedupe, review 실패, backslash escape, 실행별 artifact 계약을 검증합니다. 최종적으로 `uv run pytest -q`는 54 passed, `uv run ruff check src tests`는 All checks passed, `uv run basedpyright`는 0 errors를 반환했습니다.
