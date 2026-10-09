#!/bin/sh
# Run the evaluator smoke gate locally; candidate code always crosses the launcher.
set -eu

usage() {
    echo "Usage: $0 --profile PROFILE --version VERSION --digest DIGEST [--workspace DIR]" >&2
    exit 2
}

profile=
version=
digest=
workspace=.
launcher=scripts/course-sandbox
while [ "$#" -gt 0 ]; do
    case "$1" in
        --profile) [ "$#" -ge 2 ] || usage; profile=$2; shift 2 ;;
        --version) [ "$#" -ge 2 ] || usage; version=$2; shift 2 ;;
        --digest) [ "$#" -ge 2 ] || usage; digest=$2; shift 2 ;;
        --workspace) [ "$#" -ge 2 ] || usage; workspace=$2; shift 2 ;;
        *) usage ;;
    esac
done

[ -n "$profile" ] && [ -n "$version" ] && [ -n "$digest" ] || usage
[ -f "$workspace/evaluator.py" ] || { echo "ERROR: evaluator.py is missing" >&2; exit 2; }
[ -f "$workspace/verify.py" ] || { echo "ERROR: verify.py is missing" >&2; exit 2; }
[ ! -L "$workspace" ] && [ ! -L "$workspace/evaluator.py" ] && [ ! -L "$workspace/verify.py" ] || {
    echo "ERROR: candidate files must not be symlinks" >&2
    exit 2
}
[ -f "$launcher" ] || { echo "ERROR: launcher is missing" >&2; exit 2; }

run_workspace=$(mktemp -d "${TMPDIR:-/tmp}/evaluator-regression.XXXXXX")
result=$(mktemp "${TMPDIR:-/tmp}/evaluator-result.XXXXXX")
cleanup() {
    rm -rf "$run_workspace" "$result"
}
trap cleanup EXIT HUP INT TERM

# Copy only the public candidate and verification entry point into the launcher workspace.
cp "$workspace/evaluator.py" "$workspace/verify.py" "$run_workspace/"
set +e
sh "$launcher" --profile "$profile" --version "$version" --digest "$digest" \
    --workspace "$run_workspace" -- python verify.py >"$result"
launcher_status=$?
set -e
cat "$result"
# The launcher wrapper normalizes candidate failures to status 1. Parse its JSON record
# so the local gate preserves the candidate exit code while still failing infrastructure errors.
set +e
record_status=$(python3 - "$result" <<'PY'
import json
import sys
from pathlib import Path

record = json.loads(Path(sys.argv[1]).read_text())
status = record.get("exit_code")
if type(status) is not int or status < 0 or status > 125:
    raise SystemExit(2)
print(status)
PY
)
parser_status=$?
set -e
if [ "$parser_status" -eq 0 ]; then
    exit "$record_status"
fi
if [ "$launcher_status" -ne 0 ]; then
    exit "$launcher_status"
fi
exit 2
