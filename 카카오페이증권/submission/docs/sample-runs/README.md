# Sample Runs (심사자용 정제 예시)

이 폴더는 `mts-stability-guard` 파이프라인의 대표 실행 예시를 심사자가 볼 수 있도록
정제해 동봉한 것입니다.

## 왜 `input/`·`output/`이 아니라 여기인가

본 제출물은 패키징 청결성 계약 `test_submission_tree_has_no_generated_artifacts`
(`src/skills/mts-stability-guard/tests/test_packaging_cleanliness.py`)로
**패키징 트리에 이름이 `input`/`output`인 생성물 디렉터리가 없어야 함**을 스스로 강제합니다.
따라서 실제 실행 산출물(`input/`, `output/`)은 `.gitignore`로 공개 트리에서 제외되고,
런타임 증빙은 `logs/submission-evidence.jsonl` 단일 정제 라인으로만 노출됩니다.

심사 편의를 위한 실행 예시는 그 계약을 깨지 않도록 `input`/`output`이 아닌
이 `docs/sample-runs/` 아래에, run별 평면 구조로 담았습니다.

## 정제 내용

- `state.json`의 `input_path`/`config_path`/산출물 경로에 있던 로컬 홈 절대경로
  (`/Users/<사용자>/…/ax-hackathon/…` 형태)를 상대경로(`./카카오페이증권/…`)로 치환했습니다.
- 그 외 파일 내용은 실제 실행 결과 그대로입니다.

## 예시 목록

각 run 폴더는 입력 2개와 산출물 4개를 함께 담습니다.

| run | 시나리오 |
|---|---|
| `ulw-happy` | 정상 입력 happy-path 실행 |
| `ulw-happy-remediation` | happy-path 후 remediation 실행 |
| `docs-qa-20260709` | 문서 QA 실행 |

- 입력: `incidents.json`, `stability-config.json`
- 산출물: `analysis.json`, `chaos.json`, `scenario-checklist.md`, `state.json`
