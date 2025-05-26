from typing import ClassVar, Type, Optional, List
from pydantic import Field, model_validator, PrivateAttr

from moatless.actions.action import Action
from moatless.actions.model import ActionArguments, FewShotExample, Observation
from moatless.completion.model import StructuredOutput  # ✅ 新增
from moatless.tools.code_browser import CodeBrowser
from moatless.file_context import FileContext
from moatless.workspace import Workspace


class ExtractFunctionArgs(ActionArguments, StructuredOutput):  # ✅ 结构化动作支持
    file: str = Field(..., description="函数或类所在的源代码文件路径")
    function_name: str = Field(..., description="函数名或类名")
    thoughts: Optional[str] = Field(None, description="为什么要提取该函数？")

    @model_validator(mode="after")
    def validate_names(self) -> "ExtractFunctionArgs":
        if not self.function_name.strip():
            raise ValueError("function_name 不能为空")
        return self

    def to_prompt(self) -> str:
        return f"请从文件 {self.file} 中提取函数或类 {self.function_name} 的完整定义。"

    def short_summary(self) -> str:
        return f"ExtractFunctionSource(file={self.file}, function_name={self.function_name})"

    class Config:
        title = "ExtractFunctionSource"


class ExtractFunctionSource(Action):
    name: ClassVar[str] = "ExtractFunctionSource"
    description: ClassVar[str] = "从指定 C/C++ 源文件中提取函数或类的完整定义"
    args_schema: ClassVar[Type[ActionArguments]] = ExtractFunctionArgs

    _browser: CodeBrowser = PrivateAttr()

    def __init__(self):
        super().__init__()
        self._browser = CodeBrowser()

    def _execute(
        self,
        args: ExtractFunctionArgs,
        file_context: FileContext,
        workspace: Workspace,
    ) -> Observation:
        print(f"[EXECUTE DEBUG] 🧠 ExtractFunctionSource running")
        print(f"  📄 Target file: {args.file}")
        print(f"  🔍 Target function/class: {args.function_name}")
        try:
            source = self._browser.code_browser_source(args.file, args.function_name)
            print(f"  ✅ Extraction succeeded. Source length: {len(source)} chars")
            return Observation(
                message=source,
                summary=f"{args.function_name} 提取成功，共 {len(source.splitlines())} 行",
                extra={
                    "extracted_from": args.file,
                    "target": args.function_name,
                },
                expect_correction=False,
            )
        except Exception as e:
            return Observation(
                message=f"函数提取失败: {e}",
                summary="函数提取失败，可能函数名拼写错误或未能解析",
                extra={"error": True, "target": args.function_name},
                expect_correction=True,
            )

    @classmethod
    def get_few_shot_examples(cls) -> List[FewShotExample]:
        return [
            FewShotExample.create(
                user_input="请提取 example.cpp 中的 test_case 函数源码",
                action=ExtractFunctionArgs(
                    file="example.cpp",
                    function_name="test_case",
                    thoughts="test_case 是测试是否触发溢出的关键函数，需了解其逻辑",
                ),
            ),
            FewShotExample.create(
                user_input="main.cpp 里的 handle_request 函数实现在哪儿？",
                action=ExtractFunctionArgs(
                    file="main.cpp",
                    function_name="handle_request",
                    thoughts="我们需要定位请求处理逻辑中的潜在风险点",
                ),
            ),
        ]
