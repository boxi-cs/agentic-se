"""Week 11 public fixture: ask the launcher's model broker for replies, one at a time.

Course-authored synthetic practice. Run it only through the course launcher with the FAKE
model option. It sends fixed synthetic prompts, prints how many characters came back and
never prints, stores or sends anything else.
"""

import sys

from sandbox_model import chat

LARGEST_REQUEST_COUNT = 10


def main(argv: list[str]) -> int:
    """Make the requested number of prompt-only calls, reporting each before the next."""
    if len(argv) != 2 or not (argv[1].isascii() and argv[1].isdigit()):
        print("usage: python gateway_probe.py COUNT")
        return 2
    wanted = int(argv[1])
    if not 1 <= wanted <= LARGEST_REQUEST_COUNT:
        print(f"COUNT must be between 1 and {LARGEST_REQUEST_COUNT}")
        return 2
    for number in range(1, wanted + 1):
        reply = chat(f"Week 11 synthetic request {number}: reply with one short sentence.")
        print(f"request {number}: received {len(reply)} characters", flush=True)
    print(f"completed {wanted} requests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
