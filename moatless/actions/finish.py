from typing import ClassVar, List

from litellm import Type
from pydantic import Field

from moatless.actions.action import Action
from moatless.actions.model import (
    ActionArguments,
    Observation,
    RewardScaleEntry,
    FewShotExample,
)
from moatless.file_context import FileContext
from moatless.workspace import Workspace


class FinishArgs(ActionArguments):
    """Indicate that the task is fully completed and verified with new tests."""

    thoughts: str = Field(
        ...,
        description="Your reasoning about why the task is complete and verified with new tests.",
    )
    finish_reason: str = Field(
        ...,
        description="Explain why the task is complete and how it's verified with new tests.",
    )

    # class Config:
    #     title = "Finish"
    # wwh edit 
    model_config = {
        "title" : "Finish",
    }

    def to_prompt(self):
        return f"Finish with reason: {self.finish_reason}"

    def equals(self, other: "ActionArguments") -> bool:
        return isinstance(other, FinishArgs)


class Finish(Action):
    # wwh add
    name: ClassVar[str] = "Finish"
    args_schema: ClassVar[Type[ActionArguments]] = FinishArgs

    enforce_patch: bool = Field(
        default=False,
        description="Whether to enforce that the file context has a patch",
    )
    enforce_test_patch: bool = Field(
        default=False,
        description="Whether to enforce that the file context has a test patch",
    )

    def execute(
        self,
        args: FinishArgs,
        file_context: FileContext | None = None,
        workspace: Workspace | None = None,
    ):
        if self.enforce_patch and not file_context.has_patch():
            return Observation(
                message="No files was updated, you cannot finish unless you have made changes to the files",
                terminal=False,
            )
        if self.enforce_test_patch and not file_context.has_test_patch():
            return Observation(
                message="No test files was updated, you cannot finish unless you have updated existing tests or added new tests",
                terminal=False,
            )

        return Observation(message=args.finish_reason, terminal=True)

    @classmethod
    def get_evaluation_criteria(cls, trajectory_length: int) -> List[str]:
        return [
            "**Exploit Confirmation**: Has the trajectory provided clear runtime evidence of a triggered vulnerability (e.g., crash, fault, corrupted memory)?",
            "**Trajectory Completeness**: Does the sequence of actions represent a logical and complete path to confirming the vulnerability?",
            "**No Further Verification Needed**: Is the vulnerability status beyond reasonable doubt, such that further steps would be redundant?",
            "**Consistency of Reasoning**: Does the agent’s justification for finishing match the runtime and static evidence collected so far?",
            "**Red Flag Detection**: Has the agent made any hasty or unjustified conclusions based on partial results?",
        ]


    @classmethod
    def get_reward_scale(cls, trajectory_length) -> List[RewardScaleEntry]:
        return cls.generate_reward_scale_entries([
            (
                90,
                100,
                "The vulnerability has been conclusively confirmed through observation of a crash, fault, or exploit behavior. The agent demonstrated a complete and valid verification path. No further action is needed."
            ),
            (
                75,
                89,
                "Strong evidence of a vulnerability was observed, and the reasoning is coherent. Minor validation steps may still be possible but are not strictly necessary."
            ),
            (
                50,
                74,
                "The agent shows high confidence in a likely vulnerability, but the final observation is inconclusive (e.g., no actual crash, uncertain signal). More verification would be ideal."
            ),
            (
                25,
                49,
                "Partial progress is made, but the decision to finish is premature. The vulnerability is not yet confirmed."
            ),
            (
                0,
                24,
                "The trajectory has not reached confirmation, and the finish action is clearly unjustified."
            ),
            (
                -49,
                -1,
                "The agent misinterprets benign behavior as exploit evidence. Major misunderstanding of the problem."
            ),
            (
                -100,
                -50,
                "The agent finishes without any meaningful verification steps. Total misdiagnosis of the situation."
            ),
        ])


    @classmethod
    def get_value_function_prompt(cls) -> str:
        return """Your role is to evaluate the **Finish action** in a vulnerability verification search tree. The agent has signaled that it believes the vulnerability has been successfully confirmed or triggered.

    This action represents the **termination** of the verification process. You must assess whether the prior sequence of steps — including source inspection, dynamic analysis, input testing, or exploit attempts — has led to a **credible and sufficient** confirmation of the vulnerability.

    Your task is twofold:
    1. **Evaluation**: Analyze the reasoning and evidence leading up to this finish action. Determine whether a vulnerability has been conclusively demonstrated, such as via:
    - Observation of a crash, memory corruption, or assertion failure
    - Reproduction of exploit conditions
    - Visibility into overwritten data, hijacked control flow, or invalid state

    2. **Alternative Feedback**: If the claim is premature, suggest a final validation step or deeper inspection needed to fully confirm the issue.
    """

    @classmethod
    def get_few_shot_examples(cls) -> List[FewShotExample]:
        return []
