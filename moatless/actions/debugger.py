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
    file: str = Field(..., description="已编译的可执行文件路径")
    source: str = Field(..., description="源代码文件路径")
    line: int = Field(..., description="设置断点的源码行号")
    input: Optional[str] = Field("", description="输入数据（多个输入用逗号分隔）")
    exprs: Optional[str] = Field("", description="感兴趣的变量或表达式，用逗号分隔")

    def to_prompt(self) -> str:
        return f"debugger('{self.file}', '{self.source}', {self.line}, '{self.input}', '{self.exprs}')"

    def short_summary(self) -> str:
        return f"debugger({self.source}:{self.line})"

    class Config:
        title = "debugger"

    # @model_validator(mode="after")
    # def validate_inputs(self) -> "DebuggerArgs":
    #     if not self.file or not os.path.exists(self.file):
    #         raise ValueError("可执行文件路径无效")
    #     if not self.source or not os.path.exists(self.source):
    #         raise ValueError("源文件路径无效")
    #     return self


class Debugger(Action):
    name: ClassVar[str] = "debugger"
    description: ClassVar[str] = "使用 GDB 调试指定行并打印关键表达式信息"
    args_schema: ClassVar[Type[ActionArguments]] = DebuggerArgs

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
                user_input="在 test.cpp 的第45行断点并查看变量 buffer",
                action=DebuggerArgs(
                    file="./test", source="test.cpp", line=45, input="A", exprs="buffer"
                ),
            ),
            FewShotExample.create(
                user_input="调试 test2 并在 125 行查看 i, buffer[0]",
                action=DebuggerArgs(
                    file="./test2", source="vuln.cpp", line=125, input="1,2,3", exprs="i, buffer[0]"
                ),
            ),
        ]
