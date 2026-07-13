#!/usr/bin/env python3
import contextlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_ROOT, "scripts"))

import analyze_incidents as ai  # noqa: E402
from io_contract import SubmissionIOTestCase  # noqa: E402


class AnalyzeStageTest(SubmissionIOTestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ai.load(ai.DEFAULT_INPUT)
        cls.result = ai.analyze(cls.data)

    def test_incident_total_matches_sample(self):
        self.assertEqual(self.result["incident_total"], 5)

    def test_pattern_distribution_is_factual(self):
        dist = self.result["pattern_distribution"]
        # 샘플: 내부 시스템 장애 2건, 나머지 3패턴 각 1건
        self.assertEqual(dist["internal_system"], 2)
        self.assertEqual(sum(dist.values()), 5)
        # 분류된 모든 패턴은 플레이북에 정의돼 있어야 한다(unknown 태깅 없음).
        for pattern in dist:
            self.assertIn(pattern, ai.PATTERN_PLAYBOOK)

    def test_annual_trend_sorted_ascending(self):
        trend = self.result["annual_trend"]
        self.assertEqual(trend[0], ("2022", 4))
        years = [y for y, _ in trend]
        self.assertEqual(years, sorted(years))
        # 공개 보도 추세(매년 증가) 재현
        self.assertEqual([c for _, c in trend], [4, 9, 11, 13, 5])

    def test_scenarios_cover_each_pattern_dominant_first(self):
        scenarios = self.result["scenarios"]
        # 샘플에 등장한 4개 패턴 각각에 시나리오가 생성된다.
        self.assertEqual(len(scenarios), 4)
        # 우세 패턴(내부 시스템, 2건)이 가장 앞에 온다.
        self.assertEqual(scenarios[0]["pattern"], "internal_system")
        for s in scenarios:
            self.assertGreater(s["observed_incidents"], 0)
            self.assertTrue(s["recommended_tests"])  # 방어 항목이 매핑돼야 한다

    def test_report_separates_fact_and_interpretation(self):
        text = ai.render(self.data, self.result)
        self.assertIn("[사실]", text)   # 건수·일자·원인
        self.assertIn("[해석]", text)   # 권고 시나리오

    def test_default_playbook_is_loaded_from_config(self):
        config = ai.load_config(ai.DEFAULT_CONFIG)

        self.assertEqual(config["patterns"], ai.PATTERN_PLAYBOOK)
        self.assertEqual(
            config["patterns"]["external_broker_dependency"]["label"],
            "외부 브로커/현지 중개사 장애",
        )

    def test_custom_config_changes_recommended_tests_without_changing_facts(self):
        config = ai.load_config(ai.DEFAULT_CONFIG)
        config["patterns"]["internal_system"]["recommended_tests"] = ["custom deterministic gate"]

        result = ai.analyze(self.data, playbook=config["patterns"])

        self.assertEqual(result["incident_total"], 5)
        self.assertEqual(result["scenarios"][0]["pattern"], "internal_system")
        self.assertEqual(result["scenarios"][0]["recommended_tests"], ["custom deterministic gate"])

    def test_malformed_config_fails_before_analysis_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_config = Path(tmp) / "bad-config.json"
            bad_config.write_text('{"patterns": []}', encoding="utf-8")

            with self.assertRaises(ai.ConfigError):
                ai.load_config(str(bad_config))

    def test_deeply_nested_json_exits_cleanly_without_replacing_output(self):
        # Given
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested_input = root / "nested.json"
            json_output = root / "report.json"
            nested_input.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
            json_output.write_text("sentinel", encoding="utf-8")
            stdout_path = root / "stdout.txt"
            stderr_path = root / "stderr.txt"
            original_scanner = json.scanner.make_scanner
            original_decoder = json._default_decoder

            # When
            try:
                json.scanner.make_scanner = json.scanner.py_make_scanner
                json._default_decoder = json.JSONDecoder()
                with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
                    "w", encoding="utf-8"
                ) as stderr:
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        returncode = ai.main([
                            "--input",
                            str(nested_input),
                            "--json-out",
                            str(json_output),
                        ])
            finally:
                json.scanner.make_scanner = original_scanner
                json._default_decoder = original_decoder

            # Then
            self.assertEqual(returncode, 1)
            self.assertEqual(stdout_path.read_text(encoding="utf-8"), "")
            self.assertEqual(
                stderr_path.read_text(encoding="utf-8"),
                "error: incident JSON exceeds maximum nesting depth\n",
            )
            self.assertEqual(json_output.read_text(encoding="utf-8"), "sentinel")

    def test_malformed_pattern_entries_fail_before_analysis_success(self):
        cases = (
            {"patterns": {"internal_system": {"recommended_tests": ["probe"]}}},
            {"patterns": {"internal_system": {"label": "내부 시스템", "recommended_tests": []}}},
            {"patterns": {"internal_system": {"label": "내부 시스템", "recommended_tests": "probe"}}},
        )
        with tempfile.TemporaryDirectory() as tmp:
            for index, config in enumerate(cases):
                bad_config = Path(tmp) / f"bad-pattern-{index}.json"
                bad_config.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

                with self.subTest(index=index):
                    with self.assertRaises(ai.ConfigError):
                        ai.load_config(str(bad_config))


if __name__ == "__main__":
    unittest.main(verbosity=2)
