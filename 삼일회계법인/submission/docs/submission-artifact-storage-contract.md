# Submission Artifact Storage Contract

## 구현 계약

`src/bin/samil_independence_run.py` wrapper는 실행 단위 `run-id`를 기준으로
Codex plugin 입력값과 출력 산출물을 분리 저장한다.

- `input/<run-id>/`: 실행에 사용된 입력 CSV/JSON snapshot, `spec.md`,
  `context.md`, `state.md`.
- `output/<run-id>/`: Codex plugin 출력 산출물만 저장한다. 성공 실행은
  `report.md`, `review.md`이고, 입력 검증 실패 실행은 `error.md`이다.
- `state/memory/learning.md`: 다음 실행의 selected memory를 위한 durable
  learning 저장소이다. 실행 단위 input/output 쌍이 아니므로 `input/`과
  `output/` 아래에 만들지 않는다.

이 구조는 성공 실행과 실패 실행 모두에서 같은 run id로 input/output 쌍을
찾을 수 있게 한다.

## 검증 결과

최종 구현 기준 검증 결과는 다음과 같다.

- `uv run pytest -q`: 54 passed.
- `uv run ruff check src tests`: All checks passed.
- `uv run basedpyright`: 0 errors, 0 warnings, 0 notes.
- 수동 QA 실행 `qa-storage`: `input/qa-storage/`에는
  `audit_clients.csv`, `non_audit_services.csv`, `independence_rules.json`,
  `spec.md`, `context.md`, `state.md`가 생성됐다.
- 수동 QA 실행 `qa-storage`: `output/qa-storage/`에는 `report.md`,
  `review.md`만 생성됐다.
- 실패 테스트 실행 `pytest-failure`: `input/pytest-failure/`와
  `output/pytest-failure/error.md`가 같은 run id 쌍으로 남았다.
- `input/memory`는 존재하지 않으며, durable memory는
  `state/memory/learning.md`로 분리됐다.

관련 evidence 파일은 `.omo/evidence/task-18-final-full-suite-artifacts.txt`,
`.omo/evidence/task-15-memory-separated-root-pair.txt`,
`.omo/evidence/task-14-final-artifact-tree.txt`이다.
