"""A deliberately weak agent-style suite: only happy-path text is checked."""

from domains.validation import text


def test_text_happy_path() -> None:
    assert text("main") == "main"
