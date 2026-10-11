"""Week 11 public fixture: replay a synthetic per-run ledger through a reserving budget.

Course-authored synthetic practice with no model call, network access or file writes. The
units are course-made numbers, not prices. `Budget` below is the whole rule a gateway applies
to one run: reserve a worst-case amount before sending, settle to the actual amount after a
reply, and keep the whole reservation when a reply is lost and the outcome is unknown.
"""

import argparse
import sys
from decimal import Decimal


class BudgetExceeded(Exception):
    """A request was refused, or observed usage went past the cap."""


class Budget:
    """One run's cap: `reserve` before a request is sent, `settle` after its reply."""

    def __init__(self, cap: Decimal) -> None:
        self.cap = cap
        self.spent = Decimal(0)

    def reserve(self, amount: Decimal) -> None:
        """Refuse before sending when the worst case could pass the cap."""
        if self.spent + amount > self.cap:
            raise BudgetExceeded("Request exceeds the remaining budget.")
        self.spent += amount

    def settle(self, reserved: Decimal, actual: Decimal) -> None:
        """Replace a reservation with the observed cost; block if that passes the cap."""
        self.spent += actual - reserved
        if self.spent > self.cap:
            raise BudgetExceeded("Observed usage exceeded the budget; further calls are blocked.")


LARGEST_VALUE = 1000
LARGEST_REQUEST_COUNT = 50


def small_whole_number(text: str) -> int:
    """Accept only a small nonnegative integer, so every ledger stays readable."""
    if not (text.isascii() and text.isdigit()) or int(text) > LARGEST_VALUE:
        raise argparse.ArgumentTypeError(f"expected a whole number from 0 to {LARGEST_VALUE}")
    return int(text)


def replay(cap: int, reserve: int, actual: int, lost: set[int]) -> list[str]:
    """Return one line per request until the budget refuses one."""
    budget = Budget(Decimal(cap))
    lines = []
    for number in range(1, LARGEST_REQUEST_COUNT + 1):
        before = budget.spent
        try:
            budget.reserve(Decimal(reserve))
        except BudgetExceeded as refusal:
            lines.append(
                f"request {number}: refused before sending ({refusal}) spent {before} of {cap}"
            )
            return lines
        if number in lost:
            lines.append(
                f"request {number}: sent, reply lost, reservation of {reserve} kept; "
                f"spent {budget.spent} of {cap}"
            )
            continue
        try:
            budget.settle(Decimal(reserve), Decimal(actual))
        except BudgetExceeded as refusal:
            lines.append(f"request {number}: reply received, then blocked ({refusal})")
            return lines
        lines.append(f"request {number}: sent, reply cost {actual}; spent {budget.spent} of {cap}")
    lines.append(f"stopped after {LARGEST_REQUEST_COUNT} requests without a refusal")
    return lines


def main(argv: list[str] | None = None) -> int:
    """Print the ledger for the given synthetic cap, reservation and actual cost."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cap", type=small_whole_number, default=10)
    parser.add_argument("--reserve", type=small_whole_number, default=4)
    parser.add_argument("--actual", type=small_whole_number, default=1)
    parser.add_argument(
        "--lost-reply",
        type=small_whole_number,
        action="append",
        default=[],
        metavar="N",
        help="request number whose reply is lost; may be repeated",
    )
    args = parser.parse_args(argv)
    if args.reserve == 0 or args.actual > args.reserve:
        parser.error("use a positive reservation that is at least the actual cost")
    for line in replay(args.cap, args.reserve, args.actual, set(args.lost_reply)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
