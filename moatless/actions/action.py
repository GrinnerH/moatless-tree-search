import importlib
import logging
import pkgutil
from abc import ABC
from typing import List, Type, Tuple, Any, Dict, Optional, ClassVar

from pydantic import BaseModel, ConfigDict

from moatless.actions.model import (
    ActionArguments,
    Observation,
    RewardScaleEntry,
    FewShotExample,
)
from moatless.file_context import FileContext
from moatless.index import CodeIndex
from moatless.repository.repository import Repository
from moatless.workspace import Workspace

logger = logging.getLogger(__name__)

_actions: Dict[str, Type["Action"]] = {}


class Action(BaseModel, ABC):
    args_schema: ClassVar[Type[ActionArguments]]

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # wwh remove
    # def __init__(self, **data):
    #     super().__init__(**data)

    def execute(
        self,
        args: ActionArguments,
        file_context: FileContext | None = None,
        workspace: Workspace | None = None,
    ) -> Observation:
        """
        Execute the action.
        """
        
        message = self._execute(args, file_context=file_context, workspace=workspace)
        # print(f"[Action类中的message]：\n{message}")
        # return Observation.create(message)
        if isinstance(message, Observation):
            return message
        elif isinstance(message, str):
            return Observation(message=message)
        else:
            raise TypeError(f"Unsupported return type from _execute: {type(message)}")

    def _execute(
        self,
        args: ActionArguments,
        file_context: FileContext | None = None,
        workspace: Workspace | None = None,
    ) -> str | None:
        """
        Execute the action and return the updated FileContext.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    @property
    def name(self) -> str:
        """Returns the name of the action class as a string."""
        return self.__class__.__name__

    @classmethod
    def get_name(cls) -> str:
        """Returns the name of the action class as a string."""
        return cls.__name__
    
    #评估标准
    @classmethod
    def get_evaluation_criteria(cls, trajectory_length: int | None = None) -> List[str]:
        if trajectory_length < 3:
            return [
                "Exploratory Step: At early stages, exploratory actions (e.g., extracting functions, probing input behaviors) are valuable even without immediate results.",
            "Tool Appropriateness: Was the selected tool (e.g., CodeBrowser, debugger, script) suitable for this stage of verification?",
            "Hypothesis Formation: Does the action reflect a sound hypothesis about where a vulnerability might exist or how it might manifest?",
            ]

        else:
            return [
            "Evidence Strength: Did the action produce concrete indicators of vulnerability (e.g., crash, fault, memory corruption)?",
            "Verification Progress: Does this action measurably advance the agent's path toward confirming or rejecting a vulnerability?",
            "Redundancy Avoidance: Is the action meaningfully different from previous attempts, or is it repeating a path that already failed?",
            "Input/State Coverage: Did the action explore new inputs or execution states that had not yet been tested?",
            "Exploitability Signal: Does the observation suggest proximity to an exploitable condition (e.g., buffer overwritten, return address changed)?",
            ]

    @classmethod
    def get_reward_scale(cls, trajectory_length: int) -> List[RewardScaleEntry]:
        return [
            RewardScaleEntry(
                min_value=90,
                max_value=100,
                description="The action conclusively confirms the vulnerability (e.g., exploit triggered, memory corruption observed, critical condition met)."
            ),
            RewardScaleEntry(
                min_value=70,
                max_value=89,
                description="The action reveals strong evidence of vulnerability (e.g., crash, unsafe memory access, overwritten buffers)."
            ),
            RewardScaleEntry(
                min_value=40,
                max_value=69,
                description="The action contributes moderately to verification (e.g., extracting vulnerable code, setting a precise breakpoint, testing edge-case inputs)."
            ),
            RewardScaleEntry(
                min_value=10,
                max_value=39,
                description="The action is weakly useful or only exploratory (e.g., repeating a known step, inspecting irrelevant code)."
            ),
            RewardScaleEntry(
                min_value=-50,
                max_value=9,
                description="The action is redundant, misdirected, or fails to advance verification (e.g., repeating past failure, tool misuse, wrong context)."
            ),
        ]


    @staticmethod
    def generate_reward_scale_entries(
        descriptions: List[Tuple[int, int, str]],
    ) -> List[RewardScaleEntry]:
        """
        Generate a list of RewardScaleEntry objects based on the provided descriptions.

        Args:
            descriptions: A list of tuples, each containing (min_value, max_value, description)

        Returns:
            A list of RewardScaleEntry objects
        """
        return [
            RewardScaleEntry(min_value=min_val, max_value=max_val, description=desc)
            for min_val, max_val, desc in descriptions
        ]

    @classmethod
    def get_reward_range(cls, trajectory_length: int) -> Tuple[int, int]:
        """
        Get the minimum and maximum reward values for this action.

        Args:
            trajectory_length: The length of the current trajectory

        Returns:
            A tuple containing the minimum and maximum reward values
        """
        reward_scale = cls.get_reward_scale(trajectory_length)
        min_reward = min(entry.min_value for entry in reward_scale)
        max_reward = max(entry.max_value for entry in reward_scale)
        return min_reward, max_reward

    @classmethod
    def get_value_function_prompt(cls) -> str:
        """
        Get the base prompt for the value function.
        This method can be overridden in subclasses to provide action-specific prompts.
        """
        # wwh edit
        return """
Your role is to evaluate the **last executed action** taken by an autonomous agent traversing a search tree to validate the presence of software vulnerabilities.

The agent is working within a target program to identify and confirm the existence of memory-related or logic-based vulnerabilities. It operates using tools like code extractors, debuggers, and script execution environments. Its goal is not to fix bugs, but to **systematically test hypotheses** that can expose unsafe behaviors (e.g., buffer overflows, memory corruption, logic flaws).

Important: Rather than focusing on line-level accuracy or code edits, you should assess whether the **executed action moves the verification forward**. A forward step could mean clarifying a code structure, triggering a fault, discovering a memory inconsistency, or narrowing down a vulnerability candidate.

At this stage, the agent has not yet fully confirmed the vulnerability but is actively exploring. Your task is twofold:

1. **Evaluation**: Determine whether the most recent action meaningfully contributes to verifying a potential vulnerability. Consider:
   - Did the agent uncover suspicious memory access patterns?
   - Did the action reveal any abnormal program behavior (e.g., crashes, corrupt data)?
   - Was a relevant function, class, or execution path extracted or tested?
   - Did the inputs chosen expose new state transitions or side effects?
   - Was the selected tool appropriate and applied effectively?

2. **Alternative Feedback**: Propose a high-level alternative exploration path that could strengthen the investigation. This might involve:
   - Analyzing a different function or branch
   - Adjusting breakpoint targets or inputs
   - Testing additional edge-case inputs
   - Applying a different tool to gather complementary evidence

Avoid recommending actions already taken unless their result was incomplete. Your guidance should support diverse, hypothesis-driven verification strategies.
"""

    @classmethod
    def get_few_shot_examples(cls) -> List[FewShotExample]:
        """
        Returns a list of few-shot examples specific to this action.
        Override this method in subclasses to provide custom examples.
        """
        return []

    @classmethod
    def get_action_by_args_class(
        cls, args_class: Type[ActionArguments]
    ) -> Optional[Type["Action"]]:
        """
        Get the Action subclass corresponding to the given ActionArguments subclass.

        Args:
            args_class: The ActionArguments subclass to look up.

        Returns:
            The Action subclass if found, None otherwise.
        """

        def search_subclasses(current_class):
            if (
                hasattr(current_class, "args_schema")
                and current_class.args_schema == args_class
            ):
                return current_class
            for subclass in current_class.__subclasses__():
                result = search_subclasses(subclass)
                if result:
                    return result
            return None

        return search_subclasses(cls)

    @classmethod
    def get_action_by_name(cls, action_name: str) -> Type["Action"]:
        """
        Dynamically import and return the appropriate Action class for the given action name.
        """
        if not _actions:
            cls._load_actions()
        # for key, action_cls in _actions.items():
        #     print(f"[REGISTERED] key: {key} → class: {action_cls.__name__}")

        action = _actions.get(action_name)
        if action:
            return action

        raise ValueError(f"Unknown action: {action_name}")

    @classmethod
    def _load_actions(cls):
        actions_package = importlib.import_module("moatless.actions")

        for _, module_name, _ in pkgutil.iter_modules(actions_package.__path__):
            full_module_name = f"moatless.actions.{module_name}"
            module = importlib.import_module(full_module_name)
            for name, obj in module.__dict__.items():
                if isinstance(obj, type) and issubclass(obj, Action) and obj != Action:
                    # _actions[name] = obj
                    #wwh edit
                    key = getattr(obj, "name", obj.__name__)  # 优先使用 .name 属性
                    _actions[key] = obj
                    # print(f"_actions[key]:{_actions.keys()}")

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        repository: Repository = None,
        runtime: Any = None,
        code_index: CodeIndex = None,
    ) -> "Action":
        if isinstance(obj, dict):
            obj = obj.copy()
            action_class_path = obj.pop("action_class", None)

            if action_class_path:
                module_name, class_name = action_class_path.rsplit(".", 1)
                module = importlib.import_module(module_name)
                action_class = getattr(module, class_name)

                if repository and hasattr(action_class, "_repository"):
                    obj["repository"] = repository
                if code_index and hasattr(action_class, "_code_index"):
                    obj["code_index"] = code_index
                if runtime and hasattr(action_class, "_runtime"):
                    obj["runtime"] = runtime

                return action_class(**obj)

        return cls(**obj)

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        dump = super().model_dump(**kwargs)
        dump["action_class"] = f"{self.__class__.__module__}.{self.__class__.__name__}"
        return dump
