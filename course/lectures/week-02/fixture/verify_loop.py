"""Public practice checks for the run() you write in Week 1. Never a grade."""

import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import demo
from loop import last_check, run

NOT_WRITTEN = (
    "Write run() in loop.py first. Its docstring and the notes give the contract; "
    "these checks test it."
)


def run_is_written() -> bool:
    """Only the supplied stub counts as unwritten. A half-written run() that fails some
    other way still gets every check below reported by name."""
    try:
        run(lambda messages: {"content": "", "tool_calls": []}, "probe")
    except NotImplementedError:
        return False
    except Exception:
        return True
    return True


class LoopChecks(unittest.TestCase):
    def setUp(self) -> None:
        Path("result.txt").write_text("5\n")
        self.ids = itertools.count(1)

    def turn(self, *calls: tuple[str, dict], content: str = "") -> dict:
        """One assistant reply; every call gets an ID no earlier call used."""
        return {
            "content": content,
            "tool_calls": [
                {"id": f"c{next(self.ids)}", "name": name, "arguments": arguments}
                for name, arguments in calls
            ],
        }

    def play(self, *turns: dict, max_steps: int = 4) -> dict:
        replies = iter(turns)
        return run(lambda messages: next(replies), "Repair result.txt.", max_steps)

    @staticmethod
    def observations(result: dict) -> list[str]:
        return [m["content"] for m in result["messages"] if m["role"] == "tool"]

    def test_generate_then_verify(self) -> None:
        result = self.play(
            self.turn(("read", {"path": "result.txt"})),
            self.turn(("write", {"path": "result.txt", "content": "4\n"})),
            self.turn(("bash", {"command": "verify"})),
            self.turn(content="Verified."),
        )
        self.assertEqual(result["stop_reason"], "final")
        self.assertEqual(self.observations(result), ["5\n", "written", "verified"])
        self.assertEqual(last_check(result["messages"]), "verified")
        calls = [m["tool_calls"][0]["id"] for m in result["messages"][1:-1:2]]
        answers = [m["tool_call_id"] for m in result["messages"] if m["role"] == "tool"]
        self.assertEqual(calls, answers)

    def test_two_calls_in_one_reply_are_answered_in_order(self) -> None:
        result = self.play(
            self.turn(
                ("write", {"path": "result.txt", "content": "4\n"}),
                ("bash", {"command": "verify"}),
            ),
            self.turn(
                ("bash", {"command": "echo 5 > result.txt"}), ("read", {"path": "result.txt"})
            ),
            self.turn(content="Verified."),
        )
        roles = [m["role"] for m in result["messages"]]
        self.assertEqual(roles, ["user", *["assistant", "tool", "tool"] * 2, "assistant"])
        # Every call gets one answer, in the order the reply listed it, under its own ID.
        calls = [
            c["id"] for m in result["messages"] if m["role"] == "assistant" for c in m["tool_calls"]
        ]
        answers = [m["tool_call_id"] for m in result["messages"] if m["role"] == "tool"]
        self.assertEqual(answers, calls)
        observations = self.observations(result)
        self.assertEqual(observations[:2], ["written", "verified"])
        # A refused call has no effect and does not stop the next call in the same reply.
        self.assertTrue(observations[2].startswith("refused:"))
        self.assertEqual(observations[3], "4\n")
        self.assertEqual(last_check(result["messages"]), "verified")

    def test_the_proposer_receives_each_observation(self) -> None:
        requests = []

        def chat(messages: list[dict]) -> dict:
            requests.append(messages)
            return demo.scripted(messages)

        result = run(chat, demo.TASK)
        self.assertEqual(requests[1][-1], {"role": "tool", "tool_call_id": "c1", "content": "5\n"})
        self.assertEqual(requests[3][-1]["content"], "verified")
        self.assertEqual(
            (result["stop_reason"], last_check(result["messages"])), ("final", "verified")
        )

    def test_wrong_candidate_fails_its_check(self) -> None:
        with patch.object(demo, "CANDIDATE", "5\n"):
            result = run(demo.scripted, demo.TASK)
        self.assertEqual(self.observations(result), ["5\n", "written", "check_failed"])
        self.assertEqual(result["stop_reason"], "final")
        self.assertEqual(last_check(result["messages"]), "check_failed")

    def test_a_reply_without_tool_calls_is_final(self) -> None:
        result = self.play(self.turn(content=""))
        self.assertEqual(result["stop_reason"], "final")
        self.assertEqual(
            result["messages"],
            [
                {"role": "user", "content": "Repair result.txt."},
                {"role": "assistant", "content": "", "tool_calls": []},
            ],
        )

    def test_a_final_reply_is_not_verification(self) -> None:
        result = self.play(
            self.turn(("write", {"path": "result.txt", "content": "4\n"})),
            self.turn(content="done"),
        )
        self.assertEqual(self.observations(result), ["written"])
        self.assertEqual(result["stop_reason"], "final")
        self.assertEqual(last_check(result["messages"]), "not_run")

    def test_a_later_write_makes_the_check_stale(self) -> None:
        result = self.play(
            self.turn(("write", {"path": "result.txt", "content": "4\n"})),
            self.turn(("bash", {"command": "verify"})),
            self.turn(("write", {"path": "result.txt", "content": "5\n"})),
            self.turn(content="done"),
        )
        self.assertEqual(self.observations(result), ["written", "verified", "written"])
        self.assertEqual(last_check(result["messages"]), "not_run")

    def test_a_refused_bash_call_is_not_a_check(self) -> None:
        result = self.play(
            self.turn(("write", {"path": "result.txt", "content": "4\n"})),
            self.turn(("bash", {"command": "verify"})),
            self.turn(("bash", {"command": "echo check_failed"})),
            self.turn(content="done"),
        )
        self.assertTrue(self.observations(result)[2].startswith("refused:"))
        self.assertEqual(last_check(result["messages"]), "verified")

    def test_a_repeated_read_runs_until_the_turn_budget_ends(self) -> None:
        read = ("read", {"path": "result.txt"})
        result = self.play(*(self.turn(read) for _ in range(4)))
        self.assertEqual(result["stop_reason"], "step_limit")
        self.assertEqual(self.observations(result), ["5\n"] * 4)
        self.assertEqual(last_check(result["messages"]), "not_run")

    def test_denied_calls_become_observations_without_effects(self) -> None:
        for name, arguments in (
            ("read", {"path": "../outside.txt"}),
            ("read", {"path": "/etc/passwd"}),
            ("write", {"path": "result.txt", "content": "x" * 33}),
            ("write", {"path": "result.txt", "content": "4\ud800"}),  # cannot be encoded
            ("write", {"path": "../outside.txt", "content": "4\n"}),
            ("bash", {"command": "echo 4 > result.txt"}),
            ("bash", {"command": "verify", "path": "result.txt"}),
            ("upload", {"path": "result.txt"}),
            ("done", {}),
        ):
            with self.subTest(name=name, arguments=arguments):
                result = self.play(self.turn((name, arguments)), self.turn(content="stop"))
                tool_message = result["messages"][2]
                self.assertTrue(tool_message["content"].startswith("refused:"))
                self.assertEqual(
                    tool_message["tool_call_id"], result["messages"][1]["tool_calls"][0]["id"]
                )
                self.assertEqual(Path("result.txt").read_text(), "5\n")

    def test_malformed_replies_stop_before_any_tool_runs(self) -> None:
        write = {"name": "write", "arguments": {"path": "result.txt", "content": "4\n"}}
        for reply in (
            "not a message",
            None,
            {"content": ""},
            {"tool_calls": []},
            {"content": "", "tool_calls": [write]},
            {"content": "", "tool_calls": [{"id": "c1", **write, "extra": 1}]},
            {"content": "", "tool_calls": [{"id": "c1", "name": "write", "arguments": "4"}]},
            {"content": "", "tool_calls": [{"id": "c1", "name": ["write"], "arguments": {}}]},
            {"content": "", "tool_calls": [{"id": "c1", **write}, {"id": "c1", **write}]},
        ):
            with self.subTest(reply=reply), self.assertRaises(ValueError):
                run(lambda messages, reply=reply: reply, "Repair result.txt.")
            self.assertEqual(Path("result.txt").read_text(), "5\n")

    def test_a_reused_call_id_is_refused(self) -> None:
        read = {
            "content": "",
            "tool_calls": [{"id": "c1", "name": "read", "arguments": {"path": "result.txt"}}],
        }
        with self.assertRaises(ValueError):
            run(lambda messages: read, "Repair result.txt.")

    def test_a_missing_file_is_an_observation(self) -> None:
        Path("result.txt").unlink()
        result = self.play(self.turn(("read", {"path": "result.txt"})), self.turn(content="stop"))
        self.assertTrue(self.observations(result)[0].startswith("failed:"))

    def test_a_check_timeout_is_an_observation(self) -> None:
        with patch("loop.subprocess.run", side_effect=subprocess.TimeoutExpired("verify", 2)):
            result = self.play(
                self.turn(("bash", {"command": "verify"})), self.turn(content="stop")
            )
        self.assertTrue(last_check(result["messages"]).startswith("failed:"))

    def test_reply_parser_keeps_wrong_answers_and_numbers_calls(self) -> None:
        call = {"name": "write", "arguments": {"path": "result.txt", "content": "5\n"}}
        for text in (
            "<think>\nscratch\n</think>\n" + json.dumps({"content": "", "tool_calls": [call]}),
            "```json\n" + json.dumps({"tool_calls": [call]}) + "\n```",
        ):
            reply = demo.parse_reply(text, 2)
            self.assertEqual(reply["tool_calls"], [{"id": "t2-1", **call}])
        self.assertEqual(
            demo.parse_reply('{"content": "done"}', 3), {"content": "done", "tool_calls": []}
        )
        # A null beside tool calls is empty text; it does not change the calls.
        reply = demo.parse_reply(json.dumps({"content": None, "tool_calls": [call]}), 4)
        self.assertEqual(reply, {"content": "", "tool_calls": [{"id": "t4-1", **call}]})
        for text in ("The answer is 4", "[]", '{"tool_calls": "read"}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                demo.parse_reply(text, 1)


if __name__ == "__main__":
    # Keep disposable mutations in a temporary directory under the one you run from.
    import os

    with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
        os.chdir(directory)
        if not run_is_written():
            sys.exit(NOT_WRITTEN)
        unittest.main(verbosity=2)
