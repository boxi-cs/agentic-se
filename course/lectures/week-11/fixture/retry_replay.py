"""Week 11 public fixture: replay the retry incident against an in-memory database.

Course-authored synthetic practice with no model call, network access or file writes. A
request is a batch of rows (pipeline, operation_key, build, attempt). Three handlers:
`unprotected` inserts every delivery; `check-then-insert` looks the key up, then inserts it
if absent; `repaired` applies the same ideas as the dashboard's import rule: the key is
unique within its pipeline, one conflicting row stops the whole batch from being saved, and
a build shows the job of its greatest attempt.

Row 2 forces the race: each handler pauses just before its first write, so both requests
finish any lookup before either one writes; put any lookup you add before that pause. The
shared connection runs one statement at a time; no lock is held across a lookup and an insert.
"""

import argparse
import sqlite3
import threading
from collections.abc import Callable

MODES = ("unprotected", "check-then-insert", "repaired")
RETRY = ("alpha", "retry-B42-7", 42, 7)
# The four notes rows: two requests, sent together or not, and what the repair requires.
ROWS = (
    ([[RETRY], [RETRY]], False, "J81 J81", 1),
    ([[RETRY], [RETRY]], True, "J81 J81", 1),
    ([[RETRY], [("alpha", "retry-B42-7", 43, 7)]], False, "J81 conflict", 1),
    ([[RETRY], [("alpha", "retry-B42-8", 42, 8)]], False, "J81 J82", 2),
)
FIND = "SELECT rowid, build, attempt FROM jobs WHERE pipeline = ? AND operation_key = ?"
ONE_PAYLOAD_PER_KEY = """CREATE TRIGGER one_payload_per_key BEFORE INSERT ON jobs
WHEN EXISTS (SELECT 1 FROM jobs WHERE pipeline = NEW.pipeline
    AND operation_key = NEW.operation_key AND (build, attempt) != (NEW.build, NEW.attempt))
BEGIN SELECT RAISE(ABORT, 'conflict'); END"""


class Store:
    """One jobs table in memory; job numbers start at J81, as in the notes."""

    def __init__(self, mode: str) -> None:
        self.mode, self.statement = mode, threading.Lock()
        self.between: Callable[[], object] = lambda: None  # row 2 makes this a barrier
        self.db = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
        unique = ", UNIQUE (pipeline, operation_key)" if mode == "repaired" else ""
        self.sql(f"CREATE TABLE jobs (pipeline, operation_key, build, attempt{unique})")
        if mode == "repaired":
            self.sql(ONE_PAYLOAD_PER_KEY)

    def sql(self, query: str, params: tuple = ()) -> list[tuple]:
        """Run one statement; the shared connection serves one statement at a time."""
        with self.statement:
            return self.db.execute(query, params).fetchall()

    def insert(self, row: tuple) -> int:
        return self.sql("INSERT INTO jobs VALUES (?, ?, ?, ?) RETURNING rowid", row)[0][0]

    def handle(self, batch: list[tuple]) -> str:
        """Reply with one job per row, or with a conflict."""
        if self.mode == "unprotected":  # no identity and no batch check
            self.between()
            rowids = [self.insert(row) for row in batch]
        elif self.mode == "check-then-insert":  # a lookup, then a separate insert
            found = [(self.sql(FIND, row[:2]), row) for row in batch]
            self.between()
            if any(rows and rows[0][1:] != row[2:] for rows, row in found):
                return "conflict"
            rowids = [rows[0][0] if rows else self.insert(row) for rows, row in found]
        else:  # repaired: one statement, so the database decides for the whole batch
            self.between()
            values = ", ".join(["(?, ?, ?, ?)"] * len(batch))
            try:
                self.sql(
                    f"INSERT INTO jobs VALUES {values} ON CONFLICT DO NOTHING",
                    tuple(value for row in batch for value in row),
                )
            except sqlite3.IntegrityError:  # the trigger refused a second payload for a key
                return "conflict"
            rowids = [self.sql(FIND, row[:2])[0][0] for row in batch]
        return " ".join(f"J{80 + rowid}" for rowid in rowids)

    def shown(self, build: int) -> str:
        """The dashboard shows a build's greatest attempt; a repeated attempt, its later job."""
        top = self.sql(
            "SELECT rowid FROM jobs WHERE pipeline = 'alpha' AND build = ?"
            " ORDER BY attempt DESC, rowid DESC LIMIT 1",
            (build,),
        )
        return f"J{80 + top[0][0]}" if top else "nothing"


def together(store: Store, requests: list[list[tuple]]) -> list[str]:
    """Send requests from separate threads; each finishes any lookup before any writes."""
    gate, replies, errors = threading.Barrier(len(requests), timeout=10), [""] * len(requests), []
    store.between = gate.wait

    def deliver(index: int) -> None:
        try:
            replies[index] = store.handle(requests[index])
        except Exception as error:  # report after every thread has stopped
            errors.append(error)
            gate.abort()

    threads = [threading.Thread(target=deliver, args=(i,)) for i in range(len(requests))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise RuntimeError("a request thread failed") from errors[0]
    return sorted(replies)  # either request may write first


def replay(mode: str) -> tuple[list[str], int]:
    """Run each notes row on a fresh database; report the replies, jobs and dashboard view."""
    lines, met = [f"mode: {mode}", "row  replies       jobs (build/attempt)  build 42 shows"], 0
    for number, (requests, concurrent, required, job_count) in enumerate(ROWS, 1):
        store = Store(mode)
        replies = together(store, requests) if concurrent else [store.handle(r) for r in requests]
        jobs = store.sql("SELECT rowid, build, attempt FROM jobs")
        met += " ".join(replies) == required and len(jobs) == job_count
        listed = ", ".join(f"J{80 + rowid} {build}/{attempt}" for rowid, build, attempt in jobs)
        lines.append(f"{number:<4} {' '.join(replies):<13} {listed:<21} {store.shown(42)}")
    lines.append(f"rows meeting the repaired requirement: {met} of {len(ROWS)}")
    return lines, met


def main(argv: list[str] | None = None) -> int:
    """Print the replay; exit 0 only when every row meets the repaired requirement."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=MODES)
    lines, met = replay(parser.parse_args(argv).mode)
    print("\n".join(lines))
    return 0 if met == len(ROWS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
