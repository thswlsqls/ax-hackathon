# mts-stability-guard — 카카오페이증권 MTS·해외주식 전산장애 재발방지 Codex 플러그인

AX 해커톤 예선 제출물. 카카오페이증권이 겪는 **반복 MTS·해외주식 전산장애**(공개·검증 가능 문제)를 대상으로, 공개 장애 이력에서 실패 패턴을 추출해 릴리즈 전 회귀·부하·장애주입 테스트 시나리오와 안정성 체크리스트를 생성하는 Codex 플러그인이다.

문제 정의 근거는 공개 보도에서 직접 확인할 수 있다.

- [Daum/노컷뉴스(2026.04.14)](https://v.daum.net/v/20260414050325002): 2026년 1~3월 MTS 장애 5건, 2022~2025년 4→9→11→13건, 금감원 IT 현장점검 착수
- [MBC(2025.10.10)](https://imnews.imbc.com/news/2025/econo/article/6763918_36737.html): 2025년 10월 7~9일 미국 주식 거래 서비스 3거래일 연속 장애, 현지 중개사/내부 시스템 원인 설명
- [서울신문(2025.10.10)](https://www.seoul.co.kr/news/economy/2025/10/10/20251010016002): 국내 5개 증권사의 미국 현지 중개사 전산장애 관련 주문 지연 보도

## 디렉터리 구조
```
submission/
├── src/                                     # 플러그인 루트 (예선 규칙: 루트가 src 안)
│   ├── .codex-plugin/plugin.json            # 필수 매니페스트
│   └── skills/mts-stability-guard/
│       ├── SKILL.md                         # 스킬 정의(동작 구성요소)
│       ├── config/stability-config.json     # 실패 패턴·정책·가드레일
│       ├── scripts/analyze_incidents.py     # 1단계: config 기반 공개 이력 분석
│       ├── scripts/pipeline_memory.py       # 반복학습 memory 선택 추출
│       ├── scripts/run_pipeline.py          # 분석→chaos→state→학습 append
│       ├── demo/                            # 2단계: 재현→방어→재검증
│       │   ├── broker_mock.py               #   모의 외부 브로커(장애 주입)
│       │   ├── resilience.py                #   방어 프리미티브(서킷/재시도/폴백/백프레셔)
│       │   ├── trading_backend.py           #   naive vs guarded 주문 서비스
│       │   └── chaos_runner.py              #   before/after 완화 리포트
│       ├── tests/                           # 핵심 회귀 5개 파일 70개 + 패키징 검사 5개
│       ├── data/incidents.sample.json       # 공개 보도 기반 장애 이력 샘플
│       └── references/failure-patterns.md   # 실패 패턴 레퍼런스
├── input/                                   # 실행·테스트 단위 입력 스냅샷
├── output/                                  # 실행·테스트 단위 산출물
├── README.md
└── logs/                                    # 최종 제출 단계에서 sanitized 증빙 marker만 추가
```

## 실행
```bash
P=src/skills/mts-stability-guard
mkdir -p output/manual

# 1단계 — 공개 이력에서 실패 패턴·재발방지 시나리오 분석
python3 "$P/scripts/analyze_incidents.py" --json-out output/manual/stability-report.json

# 2단계 — 장애 재현 → 방어코드 → before/after 완화 입증
python3 "$P/demo/chaos_runner.py" --json-out output/manual/chaos-report.json

# 반복학습 파이프라인 — 분석·chaos·체크리스트·state·memory를 한 번에 기록
python3 "$P/scripts/run_pipeline.py" --run-id qa-smoke

# 검증 — 재현(무방비 실패)→완화(방어 통과) 회귀 테스트
(cd "$P/tests" && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  test_analyze_incidents test_chaos_scenarios test_pipeline_memory test_resilience test_run_pipeline)

# 패키징 검사는 생성물이 없는 새 clone/copy에서 별도 실행
PYTHONDONTWRITEBYTECODE=1 python3 "$P/tests/test_packaging_cleanliness.py"
```
전부 Python 3 표준 라이브러리만 사용하며 네트워크·추가 설치가 필요 없다.

`run_pipeline.py` 실행 입력·산출물은 다음 계약을 따른다.

```
input/
└── <RUN_ID>/
    ├── incidents.json
    └── stability-config.json
output/
├── _learnings.md
└── runs/<RUN_ID>/
    ├── analysis.json
    ├── chaos.json
    ├── scenario-checklist.md
    └── state.json
```

`state.json`은 `run_id`, `started_at`, `finished_at`, `status`, `input_path`, `config_path`, `input_artifacts`, `artifacts`, `analysis_summary`, `chaos_summary`, `error`를 포함한다. `input_artifacts`는 실행 당시 복사된 `input/<RUN_ID>/incidents.json`, `input/<RUN_ID>/stability-config.json`을 가리키며, 산출물 경로는 모두 `output/` 아래에만 기록된다. 성공한 실행만 `output/_learnings.md`의 `§0 Run tracking`에 한 줄을 append하고, 나머지 memory 섹션은 향후 incident registry·calibration·scenario note로 승격할 항목을 위한 고정 슬롯이다. 같은 `RUN_ID` 재실행은 input/output을 바꾸기 전에 실패하고, `../escape` 같은 path-like `RUN_ID`는 기록 전에 거부한다.

핵심 회귀 테스트 70개는 각 test method 단위로 `input/test-runs/<TEST_ID>/input.json`과 `output/test-runs/<TEST_ID>/output.json` 쌍을 남긴다. 별도의 패키징 검사 5개는 핵심 테스트 수 70을 기계적으로 고정하고, 생성 디렉터리·루트 리포트·바이트코드·외부 의존성·문서 placeholder가 배포본에 섞이지 않았는지 읽기 전용으로 확인한다. 패키징 검사는 실행 증거가 없는 새 clone/copy에서 수행한다.

## 예선 질문 5문항

**1. 무엇을, 누가, 어떤 상황에서 쓰나요?**
트레이딩/브로커리지 백엔드의 안정성 담당 개발자·SRE·QA가, MTS·해외주식 장애의 재발을 막기 위해 릴리즈 전 또는 장애 사후분석 시 사용한다. 공개 장애 이력을 넣으면 실패 패턴별 테스트 시나리오와 방어 설계 체크리스트를 받는다.

**2. 왜 이 문제를 선택했나요?**
카카오페이증권 MTS 전산장애는 금감원 RFARS 기준 2022→2025년 4→9→11→13건으로 매년 증가했고, 2026년 1~3월 5건으로 자료 제출 12개사 중 최다여서 금감원이 IT 현장점검에 착수했다(CBS 노컷뉴스·다음 2026.04). 공개·검증 가능하며(확신도 상), 코딩 에이전트가 실제로 재발 방지에 기여할 수 있는 문제다.

**3. 플러그인은 어떻게 작동하나요?**
config와 memory를 포함한 3단 파이프라인이다. **1단계(분석)** `analyze_incidents.py`가 공개 이력을 4개 실패 패턴으로 분류·집계한다. **2단계(재현→방어→재검증)** `demo/`가 그 패턴을 모의 브로커에 주입해 before/after를 비교한다. **3단계(기록→학습)** `run_pipeline.py`가 실행별 state와 checklist를 남기고 성공한 실행만 `_learnings.md`에 한 줄로 append한다. SKILL.md가 Codex에게 선택적 memory 추출, 사실/해석 분리, 공개·모의 데이터 한정을 지시한다.

**4. AI를 어떻게 활용했나요?**
문제 정의는 deep-research 다중 소스 검색·추출 파이프라인으로 공개 근거를 수집·구조화했고, 후보 선정은 플러그인 적합성·근거 강도·시연 가능성·임팩트 4축으로 9개 문제를 평가해 Top 1을 채택했다(`docs/카카오페이증권/deep-research-report-01.md`). AI로 스킬·실행 코드·테스트를 설계하고 공개 근거와 실행 결과를 다시 대조했다. 원본 대화·QA 기록은 로컬에만 두고 공개 Git과 플러그인 소스 패키지에서 제외한다. 최종 제출 단계의 `logs/`에는 내용이 없는 최소 sanitized 증빙 marker만 추가한다.

**5. 어떻게 검증했나요?**
"장애 재현 → 방어코드 → 재테스트 통과"를 실행 가능한 형태로 남겼다. ① `incidents.sample.json`(공개 보도 기반)으로 분석 리포트의 추세·패턴 분포를 확인했다. ② `chaos_runner.py`로 공개 장애 3패턴을 모의 브로커에 주입해, 무방비 경로는 주문 실패가 사용자에게 그대로 누출되는 반면(외부 브로커 장애 10/10, 개장 피크 12/20 유실) 방어 경로는 유실 0으로 강등·회복됨을 before/after로 입증했다. ③ `run_pipeline.py`의 state·checklist·memory 계약을 검증했다. ④ 현재 핵심 회귀 70개와 읽기 전용 패키징 검사 5개를 검증했고, 최종 제출 단계에서 계약 검사 6개를 더해 공개 검증 81개로 고정한다. 각 시나리오에 공개 출처 URL을 병기하고 사실과 해석을 분리했다.

## 근거·한계
- 모든 장애 근거는 공개 보도이며 각 레코드에 출처를 명시했다. 회사 내부 시스템·고객 데이터에는 접근하지 않는다.
- 실행은 로컬 파일만 읽고 쓰며 네트워크 요청을 만들지 않는다. 기본 파이프라인 상태는 submission의 `input/`과 `output/`에 저장되고, 설치된 플러그인 예시는 `--input-dir`과 `--output-dir`로 사용자가 지정한 작업 디렉터리를 사용한다.
- 전용 비밀정보 redaction 엔진은 구현하지 않았다. 따라서 입력은 공개 장애 자료와 모의 데이터로 제한하고, 계정·토큰·개인정보·사내 경로를 입력하거나 로그에 남기지 않는다.
- 장애 건수는 집계 창에 따라 다르다(RFARS 2022~2025=37건 vs 2022.1~2026.3=42건).
- 데모의 브로커·트레이딩 백엔드는 **공개 이력을 재현하기 위한 모의(mock) 시스템**이며 카카오페이증권 실제 인프라가 아니다. 방어 설계(서킷브레이커·재시도·폴백·백프레셔)는 이 스킬의 해석·권고이고, 실제 서비스 코드에 적용하려면 대상 시스템에 맞춘 이식이 필요하다.
- 후속 확장 대상: 외부 브로커 헬스체크 MCP 연동, 실제 부하/chaos 러너(예: 동시성·네트워크 지연 주입) 결합.
