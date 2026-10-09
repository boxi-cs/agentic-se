"""Public regression tests; execute through the course launcher."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

import demo
import repaired


class DemonstrationTests(unittest.TestCase):
    """Keep the displayed success dependent on actual candidate behavior."""

    def test_reference_observations_and_transcript(self) -> None:
        output = io.StringIO()
        with (
            patch.object(demo.Path, "write_text", autospec=True) as write,
            patch("demo.emit_artifact") as emit,
            contextlib.redirect_stdout(output),
        ):
            demo.main()
        result = json.loads(write.call_args.args[1])
        emit.assert_called_once_with("observations.json")
        self.assertEqual(result["model_requests"], 0)
        self.assertEqual(
            [row["actual"] for row in result["candidate"]],
            ["passed", "failed", "unknown", "unknown", "unknown", "unknown"],
        )
        self.assertEqual(
            [row["actual"] for row in result["repaired"]],
            ["passed", "failed", "passed", "failed", "unknown", "unknown"],
        )
        self.assertEqual(
            output.getvalue(),
            "generation: scripted-course-candidates\n"
            "candidate / ordinary: 2/2 passed\n"
            "candidate / contract: 4/6 passed\n"
            "repaired  / contract: 6/6 passed\n"
            "regression: original cases retained\n",
        )

    def test_broken_repair_cannot_print_success(self) -> None:
        output = io.StringIO()
        with patch("repaired.status_label", return_value="unknown"):
            with (
                contextlib.redirect_stdout(output),
                self.assertRaisesRegex(AssertionError, "repair violates"),
            ):
                demo.main()
        self.assertEqual(output.getvalue(), "")

    def test_changed_candidate_cannot_hide_the_expected_failures(self) -> None:
        with patch("candidate.status_label", repaired.status_label):
            with self.assertRaisesRegex(AssertionError, "expected failures"):
                demo.main()

    def test_different_failure_labels_cannot_match_the_displayed_matrix(self) -> None:
        different = ["passed", "failed", "failed", "failed", "unknown", "unknown"]
        with patch("candidate.status_label", side_effect=different):
            with self.assertRaisesRegex(AssertionError, "expected failures"):
                demo.main()

    def test_observation_calls_the_supplied_implementation(self) -> None:
        with patch("repaired.status_label", side_effect=ValueError("broken candidate")):
            with self.assertRaisesRegex(ValueError, "broken candidate"):
                demo.observe(repaired.status_label)


if __name__ == "__main__":
    unittest.main()
