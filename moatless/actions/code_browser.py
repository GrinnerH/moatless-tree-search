# moatless/actions/code_browser.py

from typing import ClassVar, Type, Optional, List
from pydantic import Field, model_validator, PrivateAttr

from moatless.actions.action import Action
from moatless.actions.model import ActionArguments, FewShotExample, Observation
from moatless.file_context import FileContext
from moatless.workspace import Workspace

from clang.cindex import Index, CursorKind
import os


class CodeBrowserArgs(ActionArguments):
    file: str = Field(..., description="C/C++ 源文件路径")
    name: str = Field(..., description="要提取的函数名或类名")
    model_config = {
        "title": "CodeBrowser",
        "description": "用于提取函数或类的源码以支持静态分析"
    }

    def to_prompt(self) -> str:
        return f"CodeBrowser('{self.file}', '{self.name}')"

    def short_summary(self) -> str:
        return f"CodeBrowser({self.file}, {self.name})"

    # class Config:
    #     title = "code_browser"
    #     description = "用于提取指定函数或类的源代码"

    @model_validator(mode="after")
    def validate_fields(self) -> "CodeBrowserArgs":
        if not self.name.strip():
            raise ValueError("name 不能为空")
        return self


class CodeBrowser(Action):
    name: ClassVar[str] = "CodeBrowser"
    description: ClassVar[str] = "提取指定函数或类的源代码（来自 C/C++ 文件）"
    args_schema: ClassVar[Type[ActionArguments]] = CodeBrowserArgs
    # args_schema: CodeBrowserArgs
    _index: Index = PrivateAttr()

    def __init__(self):
        super().__init__()
        self._index = Index.create()

    def _execute(
        self,
        args: CodeBrowserArgs,
        file_context: FileContext,
        workspace: Workspace,
    ) -> Observation:
        try:
            result = self.code_browser_source(args.file, args.name)
            return Observation(
                message=result,
                summary=f"{args.name} 提取成功，共 {len(result.splitlines())} 行",
                extra={"file": args.file, "target": args.name},
            )
        except Exception as e:
            return Observation(
                message=f"提取失败: {e}",
                summary="CodeBrowser提取失败",
                expect_correction=True,
                extra={"error": str(e)},
            )

    def code_browser_source(self, file: str, name: str) -> str:
        if not os.path.exists(file):
            raise FileNotFoundError(f"文件未找到: {file}")

        try:
            return self._get_function_body(file, name)
        except ValueError:
            return self._get_class_body(file, name)

    def _get_function_body(self, file: str, name: str) -> str:
        tu = self._index.parse(file)
        for node in tu.cursor.walk_preorder():
            if node.kind in [CursorKind.FUNCTION_DECL, CursorKind.CXX_METHOD] and node.spelling == name:
                return self._read_lines(file, node.extent.start.line, node.extent.end.line)
        raise ValueError(f"未找到函数 '{name}'")

    def _get_class_body(self, file: str, name: str) -> str:
        tu = self._index.parse(file, args=['-x', 'c++'])
        for node in tu.cursor.walk_preorder():
            if node.kind == CursorKind.CLASS_DECL and node.spelling == name:
                return self._read_lines(file, node.extent.start.line, node.extent.end.line)
        raise ValueError(f"未找到类 '{name}'")

    def _read_lines(self, file: str, start: int, end: int) -> str:
        with open(file, 'r') as f:
            lines = f.readlines()
        return ''.join(lines[start - 1:end])

    @classmethod
    def get_few_shot_examples(cls) -> List[FewShotExample]:
        return [
            FewShotExample.create(
                user_input="I want to examine the definition of the test_case function.",
                action=CodeBrowserArgs(
                    file="test3.cpp",
                    name="test_case",
                    thoughts="test_case is likely the vulnerable entry point due to the use of strcpy."
                )
            )
        ]
    
    @classmethod
    def get_value_function_prompt(cls) -> str:
        return """Your role is to evaluate the **last executed action** of the search tree that our AI agents are traversing in order to validate potential vulnerabilities in target programs.

    The agent has used the `CodeBrowser` tool to extract the source code of a function or class. This step is intended to support reasoning about the structure and behavior of the program, particularly to identify memory-unsafe constructs such as `strcpy`, unbounded loops, or pointer manipulation.

    Important: The extracted code may not by itself confirm a vulnerability, but it plays a critical role in **hypothesis generation**. Focus on whether this action logically contributes to narrowing the search space and identifying likely vulnerable regions.

    Your task is twofold:
    1. **Evaluation**: Assess whether the selected code fragment is relevant to the agent’s current vulnerability hypothesis. Did it expose suspicious logic or control/data flow elements that merit further inspection or runtime validation?
    2. **Alternative Feedback**: Suggest a more effective target or strategy for static inspection. This may involve selecting a different function, a higher-level class, or a utility function that influences input or memory handling.
    """

    @classmethod
    def get_evaluation_criteria(cls, trajectory_length: int | None = None) -> List[str]:
        if trajectory_length is not None and trajectory_length < 3:
            return [
                "Static Exploration: Early-stage extraction of functions or classes is valuable for identifying potential vulnerability locations.",
                "Target Relevance: Is the extracted code logically related to the entry point, memory handling, or user input?",
                "Search Space Coverage: Does this action expand the agent’s understanding of reachable or influential code blocks?",
            ]
        else:
            return [
                "Vulnerability Indicators: Does the extracted code contain unsafe calls (e.g., strcpy), raw pointer arithmetic, or unbounded operations?",
                "Path Narrowing: Does this help isolate a path toward exploit conditions or clarify data/control flow?",
                "Avoidance of Redundancy: Has the same code already been extracted or analyzed earlier in the trajectory?",
            ]



