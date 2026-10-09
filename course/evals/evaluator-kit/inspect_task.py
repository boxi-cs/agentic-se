"""Inspect task over already captured observations; no Inspect provider calls."""

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ModelOutput
from inspect_ai.scorer import exact
from inspect_ai.solver import Generate, Solver, TaskState, solver


@solver
def captured_output() -> Solver:
    """Adapt a course_llm/launcher observation without generating a second answer."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        state.output = ModelOutput.from_content("course-captured", state.metadata["observed"])
        return state

    return solve


@task
def evaluator_task(records: list[dict]) -> Task:
    """Map fixture IDs, labels and captured judgments to Dataset/Solver/Scorer."""
    return Task(
        dataset=[
            Sample(
                input=row["id"],
                target=row["target"],
                id=row["id"],
                metadata={"observed": row["observed"]},
            )
            for row in records
        ],
        solver=captured_output(),
        scorer=exact(),
    )
