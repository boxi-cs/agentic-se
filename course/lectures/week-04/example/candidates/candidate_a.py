# Course-written candidate for the Week 4 Implement checkpoint. No model wrote it.
def failed_ids(runs: list[tuple[int, str]]) -> list[int]:
    found = set()
    for run_id, status in runs:
        if status == "failed":
            found.add(run_id)
    return sorted(found)
