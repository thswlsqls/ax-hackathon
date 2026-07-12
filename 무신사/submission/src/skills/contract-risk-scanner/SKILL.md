---
name: contract-risk-scanner
description: 무신사 입점·납품 계약서(텍스트/PDF 추출본)에서 대규모유통업법·공정거래법상 리스크 조항을 탐지하고, 위험등급·근거 법조문·대체 문구를 제안하는 사전 리스크 점검 스킬. 사용자가 계약서 파일 경로나 계약 조항 텍스트를 주며 "리스크 조항 점검", "계약서 검토", "멀티호밍/최혜대우/판촉비 전가 조항 찾아줘"라고 할 때 사용한다. 최종 위법성 판단이 아니라 검토 우선순위 큐를 만든다. 법률 자문·기업 재무 분석에는 사용하지 않는다.
---

# 계약서 리스크 조항 스캐너

## 목적
입점·납품 계약서에서 공정거래위원회 조사 대상이 되어 온 유형의 조항을 찾아 **검토 우선순위**를 제시한다. 무신사는 2024년 8월 '멀티호밍 제한·최혜대우 요구' 의혹, 2026년 4월 '판촉비 전가·경영정보 요구·정산 지연' 의혹으로 공정위 조사를 받았다(공개 보도 근거). 이 스킬은 그런 조항을 사전에 걸러낸다.

## 전제와 한계 (반드시 지킬 것)
- 이 스킬의 출력은 **법률 자문이 아니다.** "위법"이라고 단정하지 말고, "리스크 후보 / 검토 필요 / 근거 법조문"으로만 표현한다.
- 규칙에 매칭되지 않아도 리스크가 없다고 단정하지 않는다. 매칭은 신호일 뿐이다.
- 실제 계약서가 없으면 `fixtures/`의 샘플로 데모한다. 입력이 민감정보일 수 있으니 원문을 외부로 전송하지 않는다.

## 구성 파일 위치
스크립트·규칙·샘플은 모두 **이 SKILL.md와 같은 폴더** 아래에 있다 (이하 `<스킬디렉터리>` = 이 파일이 있는 디렉터리).
- `<스킬디렉터리>/scripts/scan_contract.py` — 결정론적 스캐너 (파이썬 표준 라이브러리만 사용)
- `<스킬디렉터리>/scripts/verify_fixtures.py` — fixture와 CLI 오류 처리를 검증하는 회귀 테스트
- `<스킬디렉터리>/scripts/render_review_artifacts.py` — 실행 요청·산출물 모델, baseline sanitization, 결정론적 산출물 텍스트 렌더링을 담당하는 순수 모듈
- `<스킬디렉터리>/scripts/run_contract_review.py` — 로컬 실행 파이프라인. `input/<run-id>--input.md`와 `output/<run-id>--baseline.json`, `<run-id>--review.md`, `<run-id>--report.md`, `<run-id>--state.md`를 생성하고 `output/_learnings.md`에 실행 학습을 append
- `<스킬디렉터리>/scripts/validate_pipeline.py` — 스캐너 회귀, 산출물, privacy, 법률 문구, 금지 dependency/token, learning memory를 한 번에 검증
- `<스킬디렉터리>/scripts/test_pipeline_edges.py` — flat artifact, no-follow/exclusive write, 부분 쓰기 보존·재시도 거부를 포함한 파이프라인 엣지케이스 22건 검증
- `<스킬디렉터리>/config/musinsa-config.json` — `privacy.mode`, 산출물 경로, role 입력, report policy의 단일 기준
- `<스킬디렉터리>/roles/` — intake-normalizer, clause-adjudicator, report-writer, run-validator 역할 프롬프트
- `<스킬디렉터리>/templates/` — input/review/report/state/learnings 산출물 스키마
- `<스킬디렉터리>/rules/clause_rules.json` — 탐지 규칙 카탈로그 (스캐너가 자동으로 찾음)
- `<스킬디렉터리>/fixtures/` — 데모용 샘플 4종(리스크 포함본 A, 정비본 B, 혼합본 C, 평문) + 기대 결과(`EXPECTED.md`)
- `무신사/submission/input/<run-id>--input.md` — 실행별 입력 record
- `무신사/submission/output/_learnings.md` — append-only learning memory. 실행 전 다시 읽고, 실행 후 한 줄만 추가한다.

## 작동 절차
1. **입력 확인**: 사용자가 준 계약서 파일 경로 또는 붙여넣은 조항 텍스트를 확인한다. 파일이면 경로를, 텍스트면 임시 파일로 저장한 경로를 사용한다. 입력이 없으면 `<스킬디렉터리>/fixtures/sample_contract_01.md`로 데모한다.
2. **컨텍스트 계약 확인**: `<스킬디렉터리>/config/musinsa-config.json`을 읽고 `privacy.mode=local_only`, role별 허용 입력, report policy, `_learnings.md`의 참고 섹션을 확인한다. 계약서 파일 원문 전체를 role prompt에 넣지 않는다.
3. **결정론적 스캔 실행**: 아래 명령으로 baseline 후보를 얻는다.
   ```bash
   python3 <스킬디렉터리>/scripts/scan_contract.py <계약서파일> --format json
   ```
   출력은 `findings[]` 배열이며 각 항목에 `rule_name`, `risk`, `matched_terms`, `law_reference`, `snippet`, `suggestion`이 들어 있다.
4. **agent-spawn 루프 실행**: Codex orchestrator agent가 아래 role prompt를 각각의 bounded agent 작업으로 스폰한다. 각 agent에는 허용 입력과 출력 artifact만 전달한다.
   - `intake-normalizer`: 입력 경로, privacy mode, redaction summary를 `input.md`로 정규화한다.
   - `clause-adjudicator`: `baseline.json`의 rule id, 조항 라벨, 위험도, 매칭어, 법조문 후보, 제안 문구를 보고 `review.md`에 keep/lower/exclude/needs-human-review를 기록한다. `local_only`에서는 raw `snippet` 값을 role prompt에 전달하지 않는다.
   - `report-writer`: `review.md`, report policy, raw `snippet` 없는 sanitized baseline summary로 `report.md`를 작성한다.
   - `run-validator`: 산출물, disclaimer, 금지 문구, learning memory를 검증한다.
5. **판단 보강 (LLM의 역할)**: 스캐너는 키워드 매칭이라 오탐/누락이 있다. 각 후보를 실제 문맥으로 다시 읽고:
   - 오탐 제거: 예) "반품"이 소비자 청약철회 안내 문맥이면 부당반품 아님 → 제외하거나 신뢰도 낮춤.
   - 누락 보강: 규칙에 없어도 경쟁제한·비용전가·정보요구·정산 취지의 조항이면 새 후보로 추가하고 근거 법조문 후보를 제시한다.
   - 각 항목에 **신뢰도(높음/중간/낮음)** 를 붙인다.
6. **리포트 작성**: 최종 결과를 아래 형식의 마크다운으로 제시한다. 위험등급 '상' → '중' → '하' 순으로 정렬한다.
7. **학습 반영**: 실행 종료 전에 `output/_learnings.md`를 다시 읽고, run tracking 한 줄만 append한다. 오탐 패턴·rule gap·rewrite candidate는 명시적 근거가 있을 때만 추가한다.

## 로컬 파이프라인 명령
스킬에서 빠른 데모나 재현 가능한 산출물이 필요하면 아래 skill-first 명령을 사용한다.
```bash
python3 <스킬디렉터리>/scripts/run_contract_review.py --demo --run-id qa-demo --input-dir 무신사/submission/input --output-dir 무신사/submission/output
```
`--input-dir`와 `--output-dir`는 호출자가 미리 만든 신뢰 경계이며, 실행기는 두 디렉터리를 no-follow로 한 번만 연다.
생성 산출물:
- `무신사/submission/input/<run-id>--input.md`
- `무신사/submission/output/<run-id>--baseline.json`
- `무신사/submission/output/<run-id>--review.md`
- `무신사/submission/output/<run-id>--report.md`
- `무신사/submission/output/<run-id>--state.md`

## 출력 형식
```
# 계약서 리스크 점검 리포트
- 대상: <파일/설명>  | 탐지 조항 수: N건 (상 x / 중 y / 하 z)
> ⚠️ 본 리포트는 법률 자문이 아니라 사전 리스크 점검 결과입니다.

## 1. [상] 멀티호밍 제한 — 제N조
- 문제 조항(발췌): "..."
- 근거 법조문: 공정거래법 제45조 …
- 왜 리스크인가: (한 문장)
- 대체 문구 제안: "..." (구체 문구)
- 신뢰도: 높음/중간/낮음
...
## 종합 의견
- 우선 검토 권장 순위와, 법률 전문가 확인이 필요한 항목을 분리해 명시.
```

## 탐지 대상 조항 유형 (규칙: `<스킬디렉터리>/rules/clause_rules.json`)
| ID | 유형 | 근거 법조문 | 위험 |
|---|---|---|---|
| R01 | 멀티호밍 제한(배타조건부거래) | 공정거래법 제45조 / 제5조 | 상 |
| R02 | 최혜대우(MFN) 요구 | 공정거래법 제45조 / 제5조 | 상 |
| R03 | 판매촉진비용 전가 | 대규모유통업법 제11조 | 상 |
| R04 | 부당 반품 | 대규모유통업법 제10조 | 중 |
| R05 | 경영정보 제공 요구 | 대규모유통업법 제14조의2 | 중 |
| R06 | 대금 정산 지연·불명확 | 대규모유통업법 제8조 | 중 |
| R07 | 부당 대금 감액 | 대규모유통업법 제7조 | 중 |

규칙은 데이터(JSON)로 분리되어 있어 조문 개정·유형 추가 시 코드 수정 없이 갱신할 수 있다.

## 검증 방법
전체 회귀 검증은 아래 명령 하나로 실행한다.
```bash
python3 <스킬디렉터리>/scripts/verify_fixtures.py
```
기대 출력: `fixture verification passed: 13 scenarios`

전체 파이프라인 검증은 아래 명령 하나로 실행한다.
```bash
python3 <스킬디렉터리>/scripts/validate_pipeline.py --skill-dir <스킬디렉터리> --input-dir 무신사/submission/input --output-dir 무신사/submission/output
```
기대 출력: `pipeline validation passed`

- `<스킬디렉터리>/fixtures/sample_contract_01.md`(리스크 다수 포함)로 스캔 시 R01·R02·R03이 '상'으로 탐지되어야 한다 (전체 7건: 상 3 + 중 4).
- `<스킬디렉터리>/fixtures/sample_contract_02.md`(정비된 계약서)로 스캔 시 '상' 등급 탐지가 0건이어야 한다. 스캐너가 중 등급 3건을 내지만 이는 의도된 오탐이며, 3단계(LLM 판단 보강)에서 문맥을 읽어 최종 0건으로 걸러야 한다.
- `<스킬디렉터리>/fixtures/sample_contract_03.md`(혼합본)로 스캔 시 3건(상 1 + 중 2)만 선별 탐지되고, 파생 조항 번호 `제5조의2`가 독립 조항으로 분할되어야 한다.
- `<스킬디렉터리>/fixtures/sample_plain_clauses.txt`(조항 헤더 없는 평문)로 스캔 시 문단 분할 fallback으로 2건이 탐지되어야 한다.
- `제1조 판매 채널`, `제2조: 판매가격`, `제3조 [판매촉진]`처럼 괄호 없는 조항 제목 변형도 조항 라벨로 보존되어야 한다.
- 계약 본문에 법령 인용(`대규모유통업법 제10조`, 줄 시작의 `제10조에 따른...`)이 있어도 계약 조항 헤더로 오분할되지 않아야 한다.
- 없는 파일 입력은 exit 2와 명확한 오류 메시지를 반환하고, 빈 파일은 0건으로 정상 종료해야 한다.
- 자세한 기대 결과는 `<스킬디렉터리>/fixtures/EXPECTED.md` 참조.
