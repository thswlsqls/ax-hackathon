#!/usr/bin/env python3
import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SUBMISSION_ROOT = SKILL_ROOT.parents[2]
TEST_INPUT_ROOT = SUBMISSION_ROOT / "input" / "test-runs"
TEST_OUTPUT_ROOT = SUBMISSION_ROOT / "output" / "test-runs"


def safe_test_id(test_id):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", test_id)


class SubmissionIOTestCase(unittest.TestCase):
    def run(self, result=None):
        test_id = self.id()
        safe_id = safe_test_id(test_id)
        input_dir = TEST_INPUT_ROOT / safe_id
        output_dir = TEST_OUTPUT_ROOT / safe_id
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now(timezone.utc).isoformat()
        (input_dir / "input.json").write_text(
            json.dumps(
                {
                    "test_id": test_id,
                    "execution_unit": safe_id,
                    "started_at": started_at,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        tracked = result
        before = _counts(tracked)
        returned = super().run(result)
        after = _counts(tracked or returned)
        status = "passed" if before == after else "failed"
        (output_dir / "output.json").write_text(
            json.dumps(
                {
                    "test_id": test_id,
                    "execution_unit": safe_id,
                    "status": status,
                    "started_at": started_at,
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return returned


def _counts(result):
    if result is None:
        # 갓 생성된 TestResult의 기준선과 동일한 0 카운트. before 스냅샷이
        # result=None으로 호출돼도 통과 테스트가 failed로 기록되지 않게 한다.
        return {
            "errors": 0,
            "failures": 0,
            "skipped": 0,
            "expected_failures": 0,
            "unexpected_successes": 0,
        }
    return {
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
    }
