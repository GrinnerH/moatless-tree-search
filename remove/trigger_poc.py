from typing import ClassVar, Type, Optional, List
from pydantic import Field, model_validator

from moatless.actions.model import ActionArguments, FewShotExample, Observation
from moatless.actions.action import Action
from moatless.completion.model import StructuredOutput  # ✅ 引入结构化基类
from moatless.file_context import FileContext
from moatless.workspace import Workspace
from moatless.tools.debuggerpexpect import Debugger


class TriggerPoCArgs(ActionArguments, StructuredOutput):  # ✅ 继承 StructuredOutput
    name: ClassVar[str] = "TriggerPoC"
    thoughts: str = Field(..., description="为什么要运行这个 PoC？说明你的意图")
    target_binary: str = Field(..., description="编译后的可执行文件路径")
    source_file: str = Field(..., description="设置断点的源代码文件路径")
    break_line: int = Field(..., description="设置断点的行号")
    exprs: Optional[str] = Field(default="", description="逗号分隔的变量名，用于调试时观察")

    @model_validator(mode="after")
    def validate_paths(self) -> "TriggerPoCArgs":
        if not self.target_binary.strip().endswith(".out"):
            raise ValueError("target_binary 应该是可执行文件（如 .out）")
        if not self.source_file.strip():
            raise ValueError("source_file 不能为空")
        return self

    def to_prompt(self) -> str:
        return (
            f"请使用 GDB 调试程序 {self.target_binary}，在 {self.source_file}:{self.break_line} 设置断点，"
            f"运行 PoC 输入，检查是否触发漏洞。观察变量: {self.exprs or '无'}"
        )

    def short_summary(self) -> str:
        return f"TriggerPoC({self.source_file}:{self.break_line})"

    class Config:
        title = "TriggerPoC"


class TriggerPoC(Action):
    name: ClassVar[str] = "TriggerPoC"
    description: ClassVar[str] = "在断点处运行 PoC 并用 GDB 检查是否触发漏洞"
    args_schema: ClassVar[Type[ActionArguments]] = TriggerPoCArgs

    def _execute(
        self,
        args: TriggerPoCArgs,
        file_context: FileContext,
        workspace: Workspace,
    ) -> Observation:
        print(f"[EXECUTE DEBUG] 🔫 Running TriggerPoC on: {args.target_binary}")
        print(f"[EXECUTE DEBUG] Breakpoint at {args.source_file}:{args.break_line}")
        print(f"[EXECUTE DEBUG] Exprs to watch: {args.exprs}")

        # 获取之前生成的 PoC 输入
        poc_input = None
        if file_context.state and file_context.state.observation:
            extra = file_context.state.observation.extra or {}
            poc_input = extra.get("generated_input")
        if not poc_input and file_context.state:
            poc_input = file_context.state.message.strip()

        debugger = Debugger()
        result = debugger.debug(
            executable_file=args.target_binary,
            file=args.source_file,
            line=args.break_line,
            cmd=poc_input,
            exprs=args.exprs or "",
        )

        # 判断是否触发
        triggered = any(
            kw in result.lower()
            for kw in ["success", "overflow", "segfault", "sigsegv", "stack smashing"]
        )

        return Observation(
            message=result[:1000],
            summary="漏洞成功触发" if triggered else "未触发漏洞",
            extra={
                "triggered": triggered,
                "input_used": poc_input,
                "raw_output": result[:2000],
            },
            expect_correction=not triggered,
            terminal=triggered,
        )

    @classmethod
    def get_few_shot_examples(cls) -> List[FewShotExample]:
        return [
            FewShotExample.create(
                user_input="尝试运行 GDB 检查是否触发溢出",
                action=TriggerPoCArgs(
                    thoughts="需要验证之前构造的输入是否触发了目标函数中的栈溢出。",
                    target_binary="a.out",
                    source_file="main.cpp",
                    break_line=42,
                    exprs="buffer1, input",
                ),
            ),
            FewShotExample.create(
                user_input="触发断点并观察关键变量",
                action=TriggerPoCArgs(
                    thoughts="PoC 输入已生成，希望在 test_case 函数处中断并检查溢出是否发生。",
                    target_binary="vuln.out",
                    source_file="main.cpp",
                    break_line=35,
                    exprs="input, overflowed",
                ),
            ),
        ]
