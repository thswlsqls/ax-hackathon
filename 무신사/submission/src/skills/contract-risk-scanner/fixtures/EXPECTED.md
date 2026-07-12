# fixture 기대 결과 (검증 기준)

스캐너(`scripts/scan_contract.py`)는 결정론적이므로 아래 결과는 항상 재현된다.
재현 명령과 기대값을 함께 기록해 로그·검증 정합성을 확보한다.
아래 명령은 스킬 디렉터리(`src/skills/contract-risk-scanner/`)에서 실행한다.

## 전체 회귀 검증

```bash
python3 scripts/verify_fixtures.py
```
- **기대**: `fixture verification passed: 13 scenarios`

## 1. sample_contract_01.md (리스크 포함본)

```bash
python3 scripts/scan_contract.py fixtures/sample_contract_01.md --format json --min-risk 상
```
- **기대**: 상 등급 **3건** — `R01_multihoming`, `R02_mfn`, `R03_promo_cost`

```bash
python3 scripts/scan_contract.py fixtures/sample_contract_01.md --format json
```
- **기대**: 전체 **7건** (상 3 + 중 4: `R04_return`, `R05_biz_info`, `R06_settlement_delay`, `R07_price_deduction`)

## 2. sample_contract_02.md (정비본)

```bash
python3 scripts/scan_contract.py fixtures/sample_contract_02.md --format json --min-risk 상
```
- **기대**: 상 등급 **0건** — 경쟁제한·비용전가 성격의 고위험 조항이 정비되어 탐지되지 않는다.

```bash
python3 scripts/scan_contract.py fixtures/sample_contract_02.md --format json
```
- **기대**: 전체 **3건** (모두 중 등급: `R04_return`, `R05_biz_info`, `R06_settlement_delay`)

### ⚠️ 정비본의 중 등급 3건은 '의도된 오탐(false positive)'이다
정비본 B의 제5·6·7조는 해당 행위를 **오히려 제한·금지**하는데, 키워드("반품", "경영정보", "정산 보류")가 문장에 등장해 매칭된다. 이는 결정론적 키워드 스캐너의 한계이며, **후속 LLM 문맥 판단 단계에서 문맥을 읽어 오탐으로 걸러내야 한다.** 즉 이 fixture는 "스캐너 baseline → LLM 검토"의 2단 구조가 왜 필요한지 보여주는 검증 사례다.

기대되는 LLM 최종 판정:
- 제5조 반품 → 오탐(법정 사유·서면약정으로 한정됨). 제외 또는 신뢰도 '낮음'.
- 제6조 정보 제공 → 오탐(민감 경영정보를 제외 대상으로 명시). 제외.
- 제7조 정산 → 오탐(법정 기한 준수·보류 사유 서면화). 제외.
- 최종 리스크 조항: **0건** (정비 완료 계약서).

## 3. sample_contract_03.md (혼합본 — 부분 리스크 + 파생 조항 번호)

정비된 조항과 위험 조항이 섞인 계약서에서 위험 조항만 선별 탐지하는지, 그리고
`제5조의2` 같은 파생 조항 번호가 독립 조항으로 분할되는지 검증한다.

```bash
python3 scripts/scan_contract.py fixtures/sample_contract_03.md --format json
```
- **기대**: 전체 **3건** — 상 1건(`R01_multihoming` 제3조: "독점 공급") + 중 2건(`R06_settlement_delay` 제5조: "90일", `R07_price_deduction` **제5조의2**: "임의 공제")
- 정비된 제2조(채널 자율)·제4조(판촉비 사전 서면약정)는 탐지되지 **않아야** 한다.
- `R07`의 조항 라벨이 `제5조의2 (공제)`여야 한다 — 파생 조항 번호 분할 검증.

```bash
python3 scripts/scan_contract.py fixtures/sample_contract_03.md --format json --min-risk 상
```
- **기대**: **1건** (`R01_multihoming`) — `--min-risk` 필터 검증.

## 4. sample_plain_clauses.txt (조항 헤더 없는 평문 — 문단 분할 fallback)

'제N조' 헤더가 전혀 없는 텍스트(계약서 발췌·이메일 붙여넣기 등)에서 문단 단위
fallback 분할이 동작하는지 검증한다.

```bash
python3 scripts/scan_contract.py fixtures/sample_plain_clauses.txt --format json
```
- **기대**: 전체 **2건** — `R01_multihoming`(문단 1: "경쟁 플랫폼"), `R03_promo_cost`(문단 2: "프로모션 비용"). 조항 라벨은 `문단 1`, `문단 2`.

## 5. CLI·파서 경계조건

`scripts/verify_fixtures.py`는 fixture 외에 아래 경계조건도 함께 검증한다.

- `제1조 판매 채널`, `제2조: 판매가격`, `제3조 [판매촉진]`처럼 괄호 없는 조항 제목 변형도 독립 조항 라벨로 보존한다.
- 계약 본문에 `대규모유통업법 제10조` 같은 inline 법령 인용이나 줄 시작의 `제10조에 따른...` 인용이 등장해도 독립 계약 조항으로 오분할하지 않는다.
- 존재하지 않는 계약서 경로는 exit 2와 `계약서 파일을 찾을 수 없습니다` 메시지를 반환한다.
- 빈 파일은 예외 없이 0건으로 종료한다.
