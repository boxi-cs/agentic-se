# Course-written candidate for the Week 4 Implement checkpoint. No model wrote it.
def failed_ids(runs: list[tuple[int, str]]) -> list[int]:
    ids = []
    for run_id, status in runs:
        if status == "failed" and run_id not in ids:
            ids.append(run_id)
    return ids
