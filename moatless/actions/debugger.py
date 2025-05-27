# moatless/actions/debugger.py

import os
import subprocess
import tempfile
from typing import ClassVar, Type, Optional, List
from pydantic import Field, model_validator

import pexpect

from moatless.actions.action import Action
from moatless.actions.model import ActionArguments, FewShotExample, Observation
from moatless.file_context import FileContext
from moatless.workspace import Workspace


class DebuggerArgs(ActionArguments):
    """
    用于设置断点并调试程序状态以验证漏洞是否存在
    """
    file: str = Field(..., description="已编译的可执行文件路径")
    source: str = Field(..., description="源代码文件路径")
    line: int = Field(..., description="设置断点的源码行号")
    input: Optional[str] = Field("", description="输入数据（多个输入用逗号分隔）")
    exprs: Optional[str] = Field("", description="感兴趣的变量或表达式，用逗号分隔")

    model_config = {
        "title": "debugger",
        "description": "用于设置断点并调试程序状态以验证漏洞是否存在"
    }
    def to_prompt(self) -> str:
        return f"debugger('{self.file}', '{self.source}', {self.line}, '{self.input}', '{self.exprs}')"

    def short_summary(self) -> str:
        return f"debugger({self.source}:{self.line})"

    # class Config:
    #     title = "debugger"
    #     description = "使用 GDB 调试指定行并打印关键表达式信息"


class Debugger(Action):
    name: ClassVar[str] = "debugger"
    description: ClassVar[str] = "使用 GDB 调试指定行并打印关键表达式信息"
    args_schema: ClassVar[Type[ActionArguments]] = DebuggerArgs
    # args_schema:  DebuggerArgs

    def _execute(
        self,
        args: DebuggerArgs,
        file_context: FileContext,
        workspace: Workspace,
    ) -> Observation:
        try:
            subprocess.run(['gdb', '--version'], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return Observation(message="GDB not found", expect_correction=True)

        gdb = pexpect.spawn('gdb --quiet', encoding='utf-8', timeout=10)
        gdb.sendline("set pagination off")
        gdb.expect_exact("(gdb)")
        gdb.sendline(f"file {args.file}")
        gdb.expect_exact("(gdb)")
        gdb.sendline(f"break {os.path.abspath(args.source)}:{args.line}")
        gdb.expect_exact("(gdb)")

        if args.input:
            user_input = args.input.replace(",", "\n").replace(" ", "")
            with open("temp_gdb_input.txt", "w") as f:
                f.write(user_input)
            gdb.sendline("run < temp_gdb_input.txt")
        else:
            gdb.sendline("run")

        gdb.expect(["Breakpoint .*", pexpect.EOF, pexpect.TIMEOUT], timeout=8)

        output = gdb.before

        if "Breakpoint" not in output:
            gdb.close()
            return Observation(message="未命中断点，调试失败", expect_correction=True)

        if args.exprs:
            for expr in args.exprs.split(","):
                expr = expr.strip()
                gdb.sendline(f"print {expr}")
                gdb.expect_exact("(gdb)")
                output += f"\n>> print {expr}\n" + gdb.before.strip()

        gdb.sendline("quit")
        gdb.close()
        if os.path.exists("temp_gdb_input.txt"):
            os.remove("temp_gdb_input.txt")

        return Observation(
            message=output.strip(),
            summary="GDB 调试完成，包含表达式打印输出",
            extra={"exprs": args.exprs},
        )

    @classmethod
    def get_few_shot_examples(cls) -> List[FewShotExample]:
        return [
            FewShotExample.create(
                user_input="Set a breakpoint at the vulnerable strcpy and inspect buffer states.",
                action=DebuggerArgs(
                    file="test3",
                    source="test3.cpp",
                    line=70,
                    input="A" * 64,
                    exprs="buffer1,buffer2",
                    thoughts="We suspect buffer1 overflows and corrupts buffer2."
                )
            )
        ]
    
    @classmethod
    def get_value_function_prompt(cls) -> str:
        return """Your role is to evaluate the **last executed action** of the search tree that our AI agents are traversing in order to validate potential vulnerabilities in target programs.

    The agent has used the `debugger` tool to set a breakpoint, execute the binary with a specific input, and inspect runtime memory or register state. This step is critical in **confirming vulnerability hypotheses**, such as buffer overflows, stack corruption, or use-after-free conditions.

    Important: Focus on whether the breakpoint and expressions were chosen to provide **runtime visibility** into potential unsafe behavior. Did the execution reveal anomalies in memory layout, variable values, or control flow?

    Your task is twofold:
    1. **Evaluation**: Determine whether the debug output meaningfully advances the verification effort. Are there signs of overflow, unexpected values, invalid pointers, or other indicators of vulnerability?
    2. **Alternative Feedback**: Suggest a more informative breakpoint location, input variation, or additional expression that could better expose runtime faults or boundary violations.
    """

    @classmethod
    def get_evaluation_criteria(cls, trajectory_length: int | None = None) -> List[str]:
        if trajectory_length is not None and trajectory_length < 3:
            return [
                "Breakpoint Logic: Was the breakpoint placed near a potentially vulnerable instruction (e.g., memory copy, loop)?",
                "Input Appropriateness: Was the chosen input likely to expose unsafe behavior or trigger a bug path?",
                "Initial Runtime Insight: Did the output provide any useful state, even if not yet conclusive?",
            ]
        else:
            return [
                "Exploit Signals: Are there runtime signs of corruption (e.g., overwritten values, illegal memory access, segfault)?",
                "Instrumentation Quality: Were meaningful expressions chosen (e.g., buffer1, buffer2, registers)?",
                "New Coverage: Does this input-path-breakpoint combination yield a new state not previously observed?",
                "Divergence from Prior Failures: Is this different from previously ineffective runtime steps?",
            ]

