"""A partial suite that catches the common text boundary but not all mutants."""

from domains.validation import text


def _raises(callable_object, *args) -> None:
    try:
        callable_object(*args)
    except ValueError:
        return
    raise AssertionError("ValueError was expected")


def test_text_happy_path() -> None:
    assert text("main") == "main"


def test_text_rejects_empty() -> None:
    _raises(text, "")
