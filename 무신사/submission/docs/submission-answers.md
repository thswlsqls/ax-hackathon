# 예선 5문항 답변 — musinsa-contract-risk-scanner

## 1. 무엇을, 누가, 어떤 상황에서 쓰나요? (최대 800자)

무신사(및 유사 패션 플랫폼)의 법무·입점운영 담당자와 입점 브랜드가, 입점·납품 계약서를 새로 체결하거나 기존 계약을 개정하기 직전에 대규모유통업법·공정거래법상 문제 소지 조항을 사전 점검하는 데 씁니다. 사용자가 계약서 텍스트(또는 PDF에서 추출한 본문)를 입력하면, 플러그인은 위험 조항 목록과 인용 원문, 근거 법조문, 상·중·하 위험등급, 그리고 대체 문구 방향을 담은 리포트를 돌려줍니다. 즉 변호사 검토 이전 단계에서 어떤 조항을 먼저 봐야 하는지 우선순위를 잡아 주는 '검토 큐' 도구입니다. 계약 담당자가 수백 건의 조항을 눈으로 훑으며 리스크를 놓치는 상황, 신규 브랜드 온보딩 시 표준계약서를 빠르게 스크리닝해야 하는 상황, 규제 이슈가 불거져 기존 계약 수백 건을 짧은 기간에 전수 재점검해야 하는 상황에서 특히 유용합니다. 법무 인력이 부족한 중소 입점 브랜드 입장에서도, 자신에게 불리한 조항을 서명 전에 스스로 걸러 내는 안전장치가 됩니다. 사람이 모든 조항을 처음부터 정독하는 대신, 플러그인이 위험 신호가 있는 조항만 근거와 함께 먼저 올려 주므로 검토 범위를 좁힐 수 있습니다. 플랫폼 운영자에게는 컴플라이언스 리스크를 사전에 관리하는 수단이고, 브랜드에게는 협상력 격차를 메우는 보조 도구가 됩니다. 최종 위법성 판단이 아니라, 사람이 집중해서 봐야 할 지점을 좁혀 검토 시간을 줄이고 중요한 조항의 누락을 방지하는 것이 이 도구의 목적입니다.

## 2. 왜 이 문제를 선택했나요? (최대 800자)

무신사는 입점 브랜드 대상 '멀티호밍 제한·최혜대우 요구' 의혹으로 2024년 8월 공정거래위원회 현장조사를 받았고, 직매입 거래의 '판촉비 전가·경영정보 요구·정산 지연' 의혹으로 2026년 4월 다시 현장조사를 받았습니다. 두 사안은 모두 계약서에 제한, 비용 부담, 정보 제공, 정산 조건 같은 문장으로 남을 수 있어 단순 이미지 분석이나 평판 모니터링보다 플러그인 과제로 적합했습니다. 실제 구현도 이 특성에 맞춰 `clause_rules.json`의 7개 규칙을 공정거래법·대규모유통업법 조문과 연결하고, `scan_contract.py`가 조항 단위로 결정론적 후보를 뽑은 뒤 role-agent 검토가 오탐과 누락을 보정하도록 만들었습니다. 입력은 계약서 텍스트, 출력은 위험 조항·근거 법조문·대체 문구라 사용자 행동으로 바로 이어지고, fixture 4종과 회귀 검증으로 재현성도 확인할 수 있습니다. 또한 재무 예측처럼 비공개 수치나 가정에 크게 기대지 않고, 공개 조사 유형과 법령 문구를 기준으로 누구나 같은 입력에서 같은 baseline을 얻을 수 있습니다. `privacy.mode=local_only`와 raw snippet 제거 설계도 민감 계약서를 다루는 현업 도입 가능성을 높였습니다. 입점 브랜드에는 서명 전 협상 신호를, 무신사에는 조사·분쟁·평판 리스크를 계약 체결 전에 줄이는 큐를 제공하므로 실제성, 반복성, 자동화 가능성, 사용자 효용이 모두 높다고 판단했습니다.

참고 출처: 전자신문 https://www.etnews.com/20240826000194, 뉴데일리경제 https://biz.newdaily.co.kr/site/data/html/2024/08/26/2024082600359.html, 이투데이 https://www.etoday.co.kr/news/view/2579662, MTN https://v.daum.net/v/WqlETPWIvV

## 3. 플러그인은 어떻게 작동하나요? (최대 800자)

결정론적 스캐너, 로컬 산출물 파이프라인, role-agent 루프를 결합한 3단 구조입니다. 1단계에서 `scan_contract.py`가 계약서를 '제N조' 단위 조항으로 분할하고, 조항 헤더가 없으면 문단 단위로 나눈 뒤, `clause_rules.json`에 정의된 7개 규칙의 트리거 키워드를 매칭해 결정론적 baseline 후보를 뽑습니다. 각 규칙은 멀티호밍 제한, 최혜대우, 판촉비 전가, 부당 반품, 경영정보 요구, 정산 지연, 부당 감액에 대응하며 대규모유통업법·공정거래법 조문에 각각 매핑돼 있습니다. 2단계에서 `run_contract_review.py`가 `config/musinsa-config.json`의 `privacy.mode=local_only`, `templates/`의 산출물 스키마, `roles/`의 입력·출력 계약, `output/_learnings.md`의 이전 실행 학습을 읽어 `input/<run-id>--input.md` 입력 record와 `output/<run-id>--baseline.json`, `<run-id>--review.md`, `<run-id>--report.md`, `<run-id>--state.md` 산출물을 생성합니다. 3단계에서 Codex orchestrator agent가 intake-normalizer, clause-adjudicator, report-writer, run-validator 역할 agent를 스폰해 오탐 제거, 누락 보강, 신뢰도 부여, report 문구 검증을 반복합니다. 계약서 파일 원문 전체는 role prompt에 넣지 않고 scanner baseline과 redaction summary를 중심 컨텍스트로 사용합니다. 규칙·프롬프트·컨텍스트·학습 메모리가 파일로 분리돼 있어 법 개정, prompt 보강, 반복 실행에서 얻은 오탐 패턴을 코드 수정 없이 반영할 수 있습니다.

## 4. AI를 어떻게 활용했나요? (최대 800자)

두 층위에서 AI를 활용했습니다. 먼저 문제 정의 단계에서 deep-research 다중 에이전트 파이프라인(웹 검색 → 출처 수집 → 주장 추출 → 교차 검증)을 돌려 공개 자료에서 무신사의 실존 문제를 도출하고, IPO 리스크와 직결된 계약·규제 문제를 대상으로 선정했습니다. 90여 개 주장을 독립 출처 간 교차 대조로 검증했고, 근거는 동봉한 `docs/deep-research-report-01.md`에 정리돼 있습니다. 다음으로 플러그인 자체가 AI와 코드의 역할을 분리해 설계됐습니다. 결정론적 스캐너는 항상 같은 결과를 내 재현성과 감사 가능성을 확보하고, LLM 검토 단계가 스캐너의 오탐·누락을 문맥으로 걸러 정확도를 높입니다. 프롬프트 엔지니어링에서는 role prompt마다 허용·금지 입력, 출력 artifact, 실패 모드, 법률 문구 guardrail을 명시했습니다. 컨텍스트 엔지니어링에서는 `config/musinsa-config.json`과 `templates/`가 각 산출물 스키마를 고정하고, `privacy.mode=local_only`에서 계약서 원문 전체가 role prompt로 넘어가지 않게 제한했습니다. 루프 엔지니어링에서는 orchestrator agent가 역할 agent를 스폰하고, 실행 후 `output/_learnings.md`를 append-only로 갱신해 다음 실행이 오탐 패턴·rule gap을 다시 읽게 했습니다. 대화 로그 제출 방식은 `logs/README.md`에 안내했으며, 공개 이력에는 세션 로그를 동봉하지 않았습니다.

## 5. 어떻게 검증했나요? (최대 800자)

`scripts/verify_fixtures.py`로 결정론적 골든 테스트 13개를 통과시켰습니다. 샘플 A는 상 3건+중 4건, `--min-risk 상`은 상 3건만 탐지해야 하고, 정비본 B는 상 0건이어야 합니다. 혼합본 C는 `제5조의2`를 포함한 위험 3건, 평문 입력은 문단 fallback 2건을 검증합니다. 괄호 없는 조항 제목 3종, 법령 인용 `제10조` 오분할 방지, 없는 파일 exit 2, 빈 파일 0건도 함께 확인했습니다. 리팩토링 후에는 `scripts/test_pipeline_edges.py`로 22개 엣지케이스를 검증합니다. run-id 충돌 시 input·output 양쪽 덮어쓰기 방지, missing input의 무부분 산출, output-only 계약, 공개 이력에 동봉한 sanitized-demo 1쌍의 input/output pair 보존, raw `snippet`의 `review.md`·`report.md` 누출 방지, `_learnings.md` append-only 보존, 검증기 2회 연속 실행, negative sample 3종 거부, bytecode cache 미생성을 확인합니다. 최종적으로 `verify_fixtures.py`, `test_pipeline_edges.py`, `validate_pipeline.py --skill-dir . --input-dir <tmp>/input --output-dir <tmp>/output` 및 negative sample 검증이 모두 exit 0으로 통과했습니다.
