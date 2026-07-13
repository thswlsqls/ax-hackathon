#!/usr/bin/env python3
"""카오스 시나리오 회귀 테스트 — before/after 완화 수치를 게이트로 고정한다.

chaos_runner.run()이 세 공개 장애 패턴에서 산출하는 완화 수치(질문지 5번의 헤드라인
근거)를 그대로 못박는다. 이 값이 바뀌면 테스트가 깨져 질문지와 데모의 정합성이 유지된다.

실행: python3 -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TEST_ROOT))
sys.path.insert(0, str(TEST_ROOT.parent))

from io_contract import SubmissionIOTestCase  # noqa: E402

# isort: split

from demo import chaos_runner  # noqa: E402


class ChaosScenarioTest(SubmissionIOTestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = chaos_runner.run()
        cls.by = {r["pattern"]: r for r in cls.results}

    def test_three_scenarios_present(self):
        self.assertEqual(len(self.results), 3)
        self.assertIn("external_broker_dependency", self.by)
        self.assertIn("overseas_latency/transient", self.by)
        self.assertIn("us_market_open_peak", self.by)

    def test_guarded_never_leaks_exception(self):
        # 모든 시나리오에서 방어 경로는 예외 누출(crashed)이 0이어야 한다.
        for r in self.results:
            self.assertEqual(r["guarded"]["crashed"], 0, msg=r["pattern"])

    def test_external_broker_outage_10_to_0(self):
        r = self.by["external_broker_dependency"]
        self.assertEqual(r["naive"]["crashed"], 10)     # 무방비: 10건 전부 누출
        self.assertEqual(r["guarded"]["deferred"], 10)  # 방어: 유실 없이 전량 보류
        self.assertEqual(r["guarded"]["filled"], 0)
        # 서킷 개방으로 브로커 호출이 재시도-only 상한(30)보다 크게 억제된다.
        self.assertLess(r["guarded_broker_calls"], 30)

    def test_transient_recovered_by_retry(self):
        r = self.by["overseas_latency/transient"]
        self.assertEqual(r["naive"]["crashed"], 6)   # 무방비: 재시도 없어 전부 실패
        self.assertEqual(r["guarded"]["filled"], 6)  # 방어: 재시도로 전량 회복
        self.assertEqual(r["guarded"]["deferred"], 0)

    def test_market_open_spike_12_shed_without_loss(self):
        r = self.by["us_market_open_peak"]
        self.assertEqual(r["naive"]["filled"], 8)
        self.assertEqual(r["naive"]["crashed"], 12)     # 무방비: 초과 12건 유실
        self.assertEqual(r["guarded"]["filled"], 8)
        self.assertEqual(r["guarded"]["deferred"], 12)  # 방어: 초과 12건 보류(유실 0)

    def test_render_marks_fact_and_interpretation(self):
        text = chaos_runner.render(self.results)
        for token in ("before", "after", "[사실]", "[해석]"):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
