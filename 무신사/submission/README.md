# musinsa-contract-risk-scanner

무신사 입점·납품 계약서에서 **대규모유통업법·공정거래법상 리스크 조항**을 탐지해, 위험등급·근거 법조문·대체 문구를 제안하는 Codex 플러그인입니다. 최종 위법성 판단이 아니라 **사전 검토 우선순위 큐**를 만듭니다.

## 디렉터리 구조
```
submission/
├── src/                                    # 플러그인 루트
│   ├── .codex-plugin/plugin.json           # 플러그인 매니페스트 (필수)
│   └── skills/contract-risk-scanner/       # 스킬 (자기완결 구성)
│       ├── SKILL.md                        # 스킬: 스캔→LLM 검토→리포트
│       ├── config/musinsa-config.json      # local_only privacy/config 단일 기준
│       ├── roles/                          # bounded role prompts
│       ├── templates/                      # 산출물/learning 스키마
│       ├── scripts/scan_contract.py        # 결정론적 조항 스캐너 (표준 라이브러리)
│       ├── scripts/verify_fixtures.py      # fixture/CLI 회귀 검증 스크립트
│       ├── scripts/run_contract_review.py  # 로컬 파이프라인 실행
│       ├── scripts/render_review_artifacts.py # 산출물 모델·결정론적 렌더링
│       ├── scripts/validate_pipeline.py    # 전체 파이프라인 검증
│       ├── scripts/test_pipeline_edges.py  # 파이프라인 엣지케이스 회귀 테스트 22건
│       ├── rules/clause_rules.json         # 조항 탐지 규칙 + 법조문 매핑
│       └── fixtures/                       # 샘플 계약서 4종 + 기대 결과(EXPECTED.md)
├── README.md
├── docs/
│   ├── deep-research-report-01.md          # 공개 자료 기반 문제 정의 보고서 (근거)
│   └── submission-answers.md               # 예선 5문항 상세 답변 (출처 URL 포함)
└── logs/README.md                          # 대화 로그 제출 안내 (세션 로그 미동봉)
submission/input/sanitized-demo/input.md    # 공개 이력에 동봉한 정제 예시 input record 중 하나
submission/output/<run-id>--{baseline.json,review.md,report.md,state.md}                 # 실행별 output artifact만 저장
submission/output/_learnings.md             # append-only 실행 학습 메모리
```

## 빠른 실행
```bash
cd src/skills/contract-risk-scanner
# 리스크 포함 샘플 → 상 3건 + 중 4건
python3 scripts/scan_contract.py fixtures/sample_contract_01.md --format md
# 상 등급만
python3 scripts/scan_contract.py fixtures/sample_contract_01.md --min-risk 상 --format json
# 정비본 → 상 0건 (중 3건은 의도된 오탐, LLM 검토 단계에서 걸러짐)
python3 scripts/scan_contract.py fixtures/sample_contract_02.md --format md
# 전체 fixture/CLI 검증 → 13개 시나리오 통과
python3 scripts/verify_fixtures.py
# 실행할수록 학습되는 로컬 파이프라인 데모
python3 scripts/run_contract_review.py --demo --run-id qa-demo --input-dir ../../../input --output-dir ../../../output
# 스캐너+산출물+privacy+문구+memory 전체 검증
python3 scripts/validate_pipeline.py --skill-dir . --input-dir ../../../input --output-dir ../../../output
# 파이프라인 엣지케이스 검증 → 22개 테스트 통과
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test_pipeline_edges.py
```
파이프라인의 `--input-dir`와 `--output-dir`는 실행 전에 생성돼 있어야 하며, 실행기는 두 루트를 no-follow로 고정한 뒤 flat artifact를 배타적으로 생성합니다. 저수준 쓰기 실패로 부분 artifact가 남으면 다른 소유자의 대체 파일을 지우지 않도록 보존하며, 해당 run-id의 재시도는 거부되므로 확인 후 새 run-id로 실행해야 합니다.
Codex에서는 플러그인을 로드한 뒤 "이 계약서 리스크 조항 점검해줘"라고 요청하면, 스킬이 스캐너를 실행하고 결과를 문맥 검토해 최종 리포트를 생성합니다.

---

## 예선 질문 5문항

### 1. 무엇을, 누가, 어떤 상황에서 쓰나요?
무신사(및 유사 패션 플랫폼)의 **법무·입점운영 담당자와 입점 브랜드**가, 입점·납품 계약서를 체결·개정하기 전에 대규모유통업법·공정거래법상 문제 소지 조항을 **사전 점검**할 때 씁니다. 계약서 텍스트를 입력하면 `input/<run-id>--input.md`에 입력 record를 남기고, `output/<run-id>--{baseline.json,review.md,report.md,state.md}`에 위험 조항·근거 법조문·대체 문구가 담긴 리포트가 나옵니다.

### 2. 왜 이 문제를 선택했나요?
무신사는 **입점 브랜드 대상 '멀티호밍 제한·최혜대우 요구' 의혹으로 2024년 8월 공정위 현장조사**를, **직매입 거래의 '판촉비 전가·경영정보 요구·정산 지연' 의혹으로 2026년 4월 현장조사**를 받았습니다(복수 언론 보도, 확신도 '상'). 이는 IPO를 앞둔 무신사의 가장 직접적인 규제 리스크입니다. 계약 조항 검토는 반복적·규칙 기반이어서 AI 플러그인으로 자동화하기에 적합합니다. 근거는 동봉한 `docs/deep-research-report-01.md`(공개 자료 기반 문제 정의 보고서)의 문제 3-1·3-2에 출처와 함께 정리돼 있습니다.

### 3. 플러그인은 어떻게 작동하나요?
3단 구조입니다. ① `scan_contract.py`가 계약서를 조항(제N조) 단위로 나눠 `clause_rules.json`의 트리거 키워드를 매칭해 **결정론적 baseline 후보**를 뽑습니다. ② `run_contract_review.py`가 `config/musinsa-config.json`, `templates/`, `roles/`, `output/_learnings.md`를 읽어 `input/<run-id>--input.md` 입력 record와 `output/<run-id>--baseline.json`·`<run-id>--review.md`·`<run-id>--report.md`·`<run-id>--state.md` 산출물을 만듭니다. ③ 스킬(`SKILL.md`)의 orchestrator agent가 intake-normalizer, clause-adjudicator, report-writer, run-validator 역할 agent를 스폰해 오탐 제거·누락 보강·신뢰도 부여·문구 검증을 반복합니다. 규칙과 컨텍스트가 파일로 분리돼 조문 개정, prompt 보강, learning 반영을 코드 수정 없이 관리할 수 있습니다.

### 4. AI를 어떻게 활용했나요?
문제 정의는 deep-research 다중 에이전트 파이프라인(웹 검색 → 출처 수집 → 주장 추출 → 교차 검증)으로 공개 자료에서 도출했고, 그 결과 IPO 리스크와 직결된 계약·규제 문제를 플러그인 대상으로 선정했습니다. 플러그인 자체도 결정론적 스캐너(재현성), role prompt 기반 LLM 문맥 판단(정확도), append-only learning memory(반복 실행 개선)를 결합해, AI가 잘하는 부분(문맥·재작성), 코드가 잘하는 부분(규칙·재현), 루프가 잘하는 부분(검증·학습 누적)을 분리했습니다. 대화 로그 제출 방식은 `logs/README.md`에 안내했으며, 공개 이력에는 세션 로그를 동봉하지 않았습니다.

### 5. 어떻게 검증했나요?
`fixtures/`에 4개 샘플(리스크 포함본 A, 정비본 B, 혼합본 C, 조항 헤더 없는 평문)과 기대 결과(`EXPECTED.md`)를 두고 `scripts/verify_fixtures.py`로 13개 시나리오를 골든 테스트로 검증해 전부 통과했습니다. A는 상 3건+중 4건, B는 상 0건, C는 위험 조항 3건만 선별 탐지(파생 조항 번호 `제5조의2` 분할 포함), 평문은 문단 fallback으로 2건이 나와야 합니다. 또한 `제1조 판매 채널`, `제2조: 판매가격`, `제3조 [판매촉진]`처럼 괄호 없는 현실적인 조항 제목 변형과 법령 인용의 `제10조`가 계약 조항 헤더로 오분할되지 않는지, 없는 파일이 exit 2를 반환하는지, 빈 파일이 0건으로 종료되는지도 확인합니다.

리팩토링 후에는 `scripts/test_pipeline_edges.py`로 파이프라인 엣지케이스 22건을 검증합니다. 기존 run-id 재실행 시 `input/<run-id>--input.md`와 `output/<run-id>--*` 어느 쪽도 덮어쓰지 않는지, 없는 입력이 부분 산출물을 남기지 않는지, `output/`에 `<run-id>--input.md`가 섞이지 않는지, 공개 이력에 동봉한 `sanitized-demo`가 `input/sanitized-demo/input.md`와 `output/sanitized-demo/baseline.json`·`review.md`·`report.md`·`state.md` 한 쌍을 갖는지 확인합니다. 또한 `baseline.json`의 raw `snippet`이 `review.md`·`report.md`로 복사되지 않는지, `_learnings.md` 기존 내용이 보존되고 실행 row가 한 번만 append되는지, `validate_pipeline.py`가 같은 입력·출력 디렉터리에서 두 번 연속 통과하는지, validator negative sample 3종이 실제로 거부되는지, `PYTHONDONTWRITEBYTECODE=1` 실행 후 `submission/src` 아래 bytecode cache가 생기지 않는지도 확인합니다. 최종 검증에서 `verify_fixtures.py`, `test_pipeline_edges.py`, `validate_pipeline.py` 반복 실행과 negative sample 검증이 모두 exit 0으로 통과했습니다. 상세는 `docs/submission-answers.md` 5번 참조.

---

## ⚠️ 한계와 책임 범위
- **법률 자문이 아닙니다.** 출력은 "리스크 후보/검토 필요/근거 법조문"까지이며, 위법 여부는 법률 전문가·공정거래위원회 판단을 따릅니다.
- 규칙 미매칭이 리스크 없음을 뜻하지 않습니다. 키워드 스캐너의 한계는 LLM 검토로 보완합니다.
- `fixtures/`의 계약서는 실제 무신사 계약서가 아닌 **데모용 창작 예시**입니다.
- 계약서 원문은 외부로 전송하지 않고 로컬에서 처리합니다.

## 근거 자료 (모두 공개 자료)
- `docs/deep-research-report-01.md` (동봉) — 공개 자료 기반 무신사 문제 정의 보고서. 문제 3-1(직매입 갑질 공정위 현장조사, 2026.4), 문제 3-2(멀티호밍 제한·최혜대우 요구 공정위 현장조사, 2024.8)
- `docs/submission-answers.md` (동봉) — 예선 5문항 상세 답변. 아래 보도의 URL 출처 포함
- 공정거래위원회 조사 관련 보도: 전자신문·뉴데일리경제(2024.8.26 멀티호밍 제한·최혜대우 현장조사), 이투데이·MTN(2026.4 대규모유통업법 위반 현장조사)
- 대규모유통업법(제7·8·10·11·14조의2)·공정거래법(제5·45조) — 국가법령정보센터(law.go.kr) 공개 법령
