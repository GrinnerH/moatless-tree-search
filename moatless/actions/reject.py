from typing import Type, ClassVar

from pydantic import Field

from moatless.actions.action import Action
from moatless.actions.model import ActionArguments, Observation, RewardScaleEntry, FewShotExample
from moatless.file_context import FileContext
from moatless.workspace import Workspace


class RejectArgs(ActionArguments):
    """Reject the task and explain why."""

    rejection_reason: str = Field(..., description="Explanation for rejection.")

    # class Config:
    #     title = "Reject"
    model_config = {
        "title": "Reject",
    }

    def to_prompt(self):
        return f"Reject with reason: {self.rejection_reason}"

    def equals(self, other: "ActionArguments") -> bool:
        return isinstance(other, RejectArgs)


class Reject(Action):
    # wwh add
    name: ClassVar[str] = "Reject"
    args_schema: ClassVar[Type[ActionArguments]] = RejectArgs

    def execute(
        self,
        args: RejectArgs,
        file_context: FileContext | None = None,
        workspace: Workspace | None = None,
    ):
        return Observation(
            message=args.rejection_reason,
            summary="Agent rejected the current path as invalid or unrelated.",
            terminal=False  # ✅ 关键改动：允许后续继续搜索分支
        )
    @classmethod
    def get_reward_scale(cls, trajectory_length: int) -> list[RewardScaleEntry]:
        return [
            RewardScaleEntry(
                min_value=20,
                max_value=30,
                description="Reject was used to abandon a misaligned or invalid approach, enabling redirection."
            ),
            RewardScaleEntry(
                min_value=0,
                max_value=19,
                description="Reject was used prematurely or without sufficient justification, slightly disruptive."
            ),
        ]

    @classmethod
    def get_evaluation_criteria(cls, trajectory_length: int | None = None) -> list[str]:
        return [
            "Reject is appropriate if the current input/task is unrelated to the described vulnerability.",
            "Reject can be used to prevent wasting effort on dead-ends or inconsistent states.",
            "Reject should avoid cutting off potentially promising paths without reason.",
        ]

    @classmethod
    def get_value_function_prompt(cls) -> str:
        return """You are evaluating the agent's decision to issue a `Reject` action in the vulnerability verification process.

The `Reject` action is not a sign of failure. It indicates the agent believes the current task or path is invalid, inconsistent, or unproductive. Your role is to determine:

1. Was the use of `Reject` justified based on the task description, code context, and exploration state?
2. Did the rejection help redirect exploration or avoid a dead end?
3. Could a better alternative be suggested for further exploration?

Reject should not prematurely terminate useful paths. A well-placed rejection supports intelligent pruning and improves overall efficiency.
"""
