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

    def to_prompt(self) -> str:
        return f"code_browser('{self.file}', '{self.name}')"

    def short_summary(self) -> str:
        return f"code_browser({self.file}, {self.name})"

    class Config:
        title = "code_browser"

    @model_validator(mode="after")
    def validate_fields(self) -> "CodeBrowserArgs":
        if not self.name.strip():
            raise ValueError("name 不能为空")
        return self


class CodeBrowser(Action):
    name: ClassVar[str] = "code_browser"
    description: ClassVar[str] = "提取指定函数或类的源代码（来自 C/C++ 文件）"
    args_schema: ClassVar[Type[ActionArguments]] = CodeBrowserArgs
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
                summary="code_browser 提取失败",
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
        tu = self.index.parse(file, args=['-x', 'c++'])
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
                user_input="提取 test.cpp 文件中的 test_case 函数源码",
                action=CodeBrowserArgs(file="test.cpp", name="test_case"),
            ),
            FewShotExample.create(
                user_input="查看 parser.h 中的 Parser 类定义",
                action=CodeBrowserArgs(file="parser.h", name="Parser"),
            ),
        ]
