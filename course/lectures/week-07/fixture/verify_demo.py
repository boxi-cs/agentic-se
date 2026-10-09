"""Public regression checks for the lesson itself; run only through course-sandbox."""

import unittest

from candidate import parse_level
from demo import (
    corpus,
    fuzz,
    mismatch,
    mutation_report,
    property_checks,
    repaired,
    strong_checks,
    unit_checks,
    weak_checks,
)


class LessonChecks(unittest.TestCase):
    def test_weak_and_valid_properties_miss_candidate_defects(self) -> None:
        weak_checks(parse_level)
        property_checks(parse_level)
        with self.assertRaises(IndexError):
            unit_checks(parse_level)
        self.assertEqual(mismatch(parse_level, "12"), "accepted_invalid_input")

    def test_repair_obeys_valid_and_invalid_contract(self) -> None:
        strong_checks(repaired)
        for text in ("", "12", "-1", "\u0663", "3\n", " ", "x"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                repaired(text)

    def test_properties_detect_a_constant_return(self) -> None:
        with self.assertRaises(AssertionError):
            property_checks(lambda text: 3)

    def test_explicit_oracle_rejects_wrong_type_and_exception(self) -> None:
        self.assertEqual(mismatch(lambda text: True, "1"), "wrong_value")
        self.assertEqual(mismatch(lambda text: 3, "x"), "accepted_invalid_input")

        def wrong_exception(text: str) -> int:
            raise RuntimeError("Synthetic failure")

        self.assertEqual(mismatch(wrong_exception, "x"), "unexpected_RuntimeError")

    def test_mutation_evidence(self) -> None:
        self.assertEqual(mutation_report(weak_checks)["killed"], 0)
        report = mutation_report(strong_checks)
        self.assertEqual(report["killed"], report["total"])
        self.assertEqual(set(report["mutants"].values()), {"killed"})

    def test_fuzz_is_bounded_repeatable_and_replayable(self) -> None:
        self.assertEqual(corpus(7), corpus(7))
        self.assertNotEqual(corpus(7), corpus(8))
        self.assertEqual(len(corpus(7)), 109)
        self.assertLessEqual(max(map(len, corpus(7))), 4)
        for seed in (0, 7, 19):
            findings = fuzz(parse_level, seed)
            self.assertEqual(findings[0], {"text": "", "reason": "unexpected_IndexError"})
            for finding in findings:
                self.assertEqual(mismatch(parse_level, finding["text"]), finding["reason"])
            self.assertEqual(fuzz(repaired, seed), [])


if __name__ == "__main__":
    unittest.main()
