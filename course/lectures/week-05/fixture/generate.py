"""Request a bounded refactoring proposal as data through the course broker."""

from pathlib import Path

from sandbox_model import chat, emit_artifact


def main() -> None:
    """Export text for inspection; never execute the model response here."""
    source = Path("before.py").read_text()
    prompt = (
        "Refactor this course synthetic Python function using a lookup dictionary. "
        "Preserve whitespace stripping, case normalization, aliases and unknown fallback. "
        "Return only the expression for its return statement, no explanation. "
        "No imports, file access, tools, dependencies or commands. /no_think\n" + source
    )
    Path("proposal.txt").write_text(chat(prompt))
    emit_artifact("proposal.txt")


if __name__ == "__main__":
    main()
