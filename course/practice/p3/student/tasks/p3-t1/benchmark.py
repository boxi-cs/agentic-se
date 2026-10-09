"""Public baseline assertions: inspect these as part of the audit."""

import json

import candidate


def main() -> None:
    suite = json.load(open("cases.json"))
    function = getattr(candidate, suite["function"])
    for case in suite["cases"]:
        args = case["args"]
        before = json.dumps(args, sort_keys=True)
        try:
            actual = function(*args)
        except ValueError:
            actual = {"raises": "ValueError"}
        assert actual == case["expected"]
        assert json.dumps(args, sort_keys=True) == before


if __name__ == "__main__":
    main()
