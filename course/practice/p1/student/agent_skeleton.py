"""Implement the loop here; the course supplies model, tool and trace adapters."""

from lab_runtime import Model, Tool, Trajectory


class Agent:
    def __init__(
        self, model: Model, tools: dict[str, Tool], max_steps: int = 4, context_limit: int = 1400
    ) -> None:
        self.model = model
        self.tools = tools
        self.max_steps = max_steps
        self.context_limit = context_limit

    def run(self, task: str) -> Trajectory:
        """Observe, request an action, execute tools, and stop with bounded context.

        Return Trajectory(messages, stop_reason), where stop_reason is final or
        step_limit. A response with no tool_calls is final, even with empty content.
        Record each response and each tool result before requesting another turn.
        See lab_runtime.compact for the supplied context adapter.
        """
        raise NotImplementedError("Implement Agent.run and verify each stopping path")
