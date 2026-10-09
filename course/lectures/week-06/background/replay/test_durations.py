"""Public checks for the duration summary. Run only through scripts/course-sandbox."""

import unittest

from durations import format_duration, median_duration


class DurationChecks(unittest.TestCase):
    def test_median_of_finished_builds(self) -> None:
        builds = [{"duration": 120}, {"duration": 60}, {"duration": 300}]
        self.assertEqual(median_duration(builds), 120)

    def test_median_of_an_even_count(self) -> None:
        self.assertEqual(median_duration([{"duration": 60}, {"duration": 120}]), 90)

    def test_no_builds(self) -> None:
        self.assertIsNone(median_duration([]))

    def test_running_build_is_left_out(self) -> None:
        builds = [{"duration": 60}, {"duration": None}, {"duration": 120}]
        self.assertEqual(median_duration(builds), 90)

    def test_format_minutes(self) -> None:
        self.assertEqual(format_duration(185), "3:05")

    def test_format_missing(self) -> None:
        self.assertEqual(format_duration(None), "-")


if __name__ == "__main__":
    unittest.main()
