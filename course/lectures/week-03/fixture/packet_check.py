"""Public formative check of a packet you built for question-2.txt. Never a grade.

No model is called and no application runs. The check reads your packet as text and asks,
for each part of the question, whether the source lines that decide it are there:

- `status`: the HTTP status of the request and the file that decides it;
- `limit`: the longest title the server accepts and the file that sets that number.

A part is `covered` when its deciding lines appear whole and in order, under a header line
that names their file, as packet B does (`legacy_app/views.py (require_user):`). It is
`no_file` when the lines are there but the header above them does not name their file,
`browser_only` (limit only) when the packet shows the browser form's limit but not the
server's, and `missing` otherwise. Spaces at either end of a line, and runs of spaces, do
not matter; a shortened or paraphrased line does not count.

The key holds SHA-256 digests of the deciding lines and file names, so reading this
script does not give the answer away; the ci-dashboard source does.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

BUDGET = 400  # Bytes of packet. With question-2.txt it stays within the 1,024-byte prompt.
# A header line starts with a file path, then a space, a colon, a parenthesis or nothing.
HEADER = re.compile(r"^([\w./-]+\.(?:py|html|md))(?=[\s:(]|$)")
KEY = {
    "status": {
        "file": "890c5ae477b80bb93bc92e85762014565e9870d33259b58781cd649a6f1e7080",
        "lines": [
            "e637a06571f2622890368b4a8e39c065ae1ff56361b209bdea67d27ffdf7ee7b",
            "7c8cabd537a4a1771c2f891e0fbd42eb88a40dcfc5fc60f2c3d0d4cebebe6962",
        ],
    },
    "limit": {
        "file": "f6846009598d86d2d266aeef9b4f794f8403dfb6f5551dbb194d211d5e1c094f",
        "lines": ["3c247cb0f955d9a2738aaf14b561b1d232fa7792cc4ebfdd99641fce23c0eede"],
        "browser_only": "5822d2b90579e282559f8f3de103e6c865fbe9e0019de7aa450e37319cbc0323",
    },
}


def digest(text: str) -> str:
    """Hash a line or file name with its spacing normalized."""
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


def quoted(packet: str) -> list[tuple[str, str | None]]:
    """Each quoted line's digest, with the digest of the file its header names, if any."""
    lines, named = [], None
    for line in packet.splitlines():
        header = HEADER.match(line)
        if header:
            named = digest(header[1].rsplit("/", 1)[-1])
        else:
            lines.append((digest(line), named))
    return lines


def label(part: dict, lines: list[tuple[str, str | None]]) -> str:
    """Label one part: covered, no_file, browser_only or missing."""
    wanted, width = part["lines"], len(part["lines"])
    runs = [lines[start : start + width] for start in range(len(lines) - width + 1)]
    found = [run for run in runs if [text for text, _ in run] == wanted]
    if any(all(named == part["file"] for _, named in run) for run in found):
        return "covered"
    if found:
        return "no_file"
    if any(text == part.get("browser_only") for text, _ in lines):
        return "browser_only"
    return "missing"


def check(packet: str) -> dict:
    """Report the packet's size against the budget and, within it, a label per part."""
    size = len(packet.encode())
    if size > BUDGET:
        return {"packet_bytes": size, "budget": BUDGET, "over_budget": True}
    lines = quoted(packet)
    parts = {name: label(part, lines) for name, part in KEY.items()}
    covered = sum(value == "covered" for value in parts.values())
    return {
        "packet_bytes": size,
        "budget": BUDGET,
        "parts": parts,
        "covered": covered,
        "of": len(KEY),
    }


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Use: packet_check.py PACKET_FILE")
    try:
        report = check(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        report = {"unreadable": True}
    print(json.dumps({"feedback_only": True, **report}, sort_keys=True))
    if "parts" not in report:
        return 2
    return 0 if report["covered"] == report["of"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
