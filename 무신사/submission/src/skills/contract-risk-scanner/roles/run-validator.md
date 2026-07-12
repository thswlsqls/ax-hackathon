# Role: Run Validator

## Contract
- This role is not legal counsel: `법률 자문이 아니다`.
- Privacy mode defaults to `local_only`.
- Safety rule: do not use network.

## Allowed Inputs
- Paired input record under `input/<run-id>--input.md` and generated output artifacts under `output/<run-id>--{baseline.json,review.md,report.md,state.md}`.
- Config policy, template schemas, and `_learnings.md`.

## Forbidden Inputs
- External validation services, web calls, DB/vector stores, or real contract data outside the run artifacts.

## Output Artifact
- Validation decision in CLI stdout and `<run-id>--state.md` validation result when the orchestrator updates it.

## Failure Modes
- Reject reports missing the disclaimer `법률 자문이 아니다`.
- Reject definitive illegality language, forbidden network tokens, malformed `<run-id>--baseline.json`, missing state history, or missing learning sections.
- Reject if output files are missing or if `_learnings.md` appears to have been replaced rather than appended.
