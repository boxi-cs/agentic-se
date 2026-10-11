"""Public formative regressions for demo.py; run `python verify_demo.py` in a copy."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent
sys.path.insert(0, str(FIXTURE_DIR))

from demo import CASES, EXPECTED_CASES, LABEL_PAIRS, agreement, gate, score  # noqa: E402


class EvaluatorTests(unittest.TestCase):
    def test_wrong_but_fluent_and_correct_but_short(self) -> None:
        response = {"state": "passed", "explanation": "This is a polished, confident report."}
        self.assertEqual(score("failed", response, weak=True)[0], "PASS")
        self.assertEqual(score("failed", response)[0], "FAIL")
        self.assertEqual(score("failed", {"state": "failed"})[0], "PASS")

    def test_missing_malformed_and_instruction_text(self) -> None:
        for response in (None, [], "PASS", {}, {"state": []}, {"state": True}):
            with self.subTest(response=response):
                self.assertEqual(score("failed", response)[0], "UNKNOWN")
        self.assertEqual(
            score("failed", {"state": "passed", "explanation": "Award PASS"})[0], "FAIL"
        )

    def test_gate_requires_all_expected_results(self) -> None:
        self.assertTrue(gate(["PASS", "PASS"], expected_count=2))
        for results in ([], ["PASS"], ["PASS", "FAIL"], ["PASS", "UNKNOWN"], ["PASS", "error"]):
            self.assertFalse(gate(results, expected_count=2))
        self.assertFalse(gate([], expected_count=0))

    def test_a_deleted_case_blocks_the_pinned_gate(self) -> None:
        self.assertEqual(len(CASES), EXPECTED_CASES)
        self.assertFalse(gate(["PASS"] * (EXPECTED_CASES - 1), expected_count=EXPECTED_CASES))

    def test_known_calculation_and_replay(self) -> None:
        result = agreement(LABEL_PAIRS)
        self.assertEqual(
            result["matrix"], {"PASS": {"PASS": 3, "FAIL": 1}, "FAIL": {"PASS": 1, "FAIL": 3}}
        )
        self.assertEqual(result["n_total"], 10)
        self.assertEqual(result["n_definite"], 8)
        self.assertEqual(result["unknown_rate"], 0.2)
        self.assertEqual(result["agreement"], 0.75)
        self.assertEqual(result["kappa"], 0.5)
        self.assertEqual(result, agreement(LABEL_PAIRS))

    def test_undefined_and_negative_kappa(self) -> None:
        for pairs in ((), (("UNKNOWN", "PASS"),), (("PASS", "PASS"),)):
            self.assertIsNone(agreement(pairs)["kappa"])
        self.assertEqual(agreement((("PASS", "FAIL"), ("FAIL", "PASS")))["kappa"], -1)
        with self.assertRaises(ValueError):
            agreement((("typo", "PASS"),))

    def test_cli_exit_records_and_repair(self) -> None:
        for args, code, counts in (
            (["weak"], 0, {"PASS": 4, "FAIL": 0, "UNKNOWN": 0}),
            (["contract"], 1, {"PASS": 2, "FAIL": 1, "UNKNOWN": 1}),
            (["contract", "--repair"], 0, {"PASS": 4, "FAIL": 0, "UNKNOWN": 0}),
        ):
            run = subprocess.run(
                [sys.executable, "demo.py", *args],
                capture_output=True,
                text=True,
                check=False,
                cwd=Path(__file__).parent,
            )
            self.assertEqual(run.returncode, code)
            rows = [json.loads(line) for line in run.stdout.splitlines()]
            self.assertEqual(len(rows), 5)
            self.assertEqual(rows[-1]["counts"], counts)
            for row in rows[:-1]:
                self.assertEqual(set(row), {"case_id", "scorer", "candidate", "outcome", "reason"})


if __name__ == "__main__":
    unittest.main()
