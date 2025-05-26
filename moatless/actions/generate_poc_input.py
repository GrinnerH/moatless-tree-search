from typing import ClassVar, Type, Optional, List
from pydantic import Field, model_validator, PrivateAttr

from moatless.actions.action import Action
from moatless.actions.model import ActionArguments, FewShotExample, Observation
from moatless.completion import CompletionModel
from moatless.completion.model import StructuredOutput  # ✅ 关键新增
from moatless.file_context import FileContext
from moatless.workspace import Workspace
from moatless.tools.scripter import ScriptRunner


class GeneratePoCInputArgs(ActionArguments, StructuredOutput):  # ✅ 继承 StructuredOutput
    file: str = Field(..., description="目标源代码文件路径，用于指定脚本运行上下文")
    script: str = Field(..., description="用于生成输入的 Python 脚本，由 LLM 编写")
    thoughts: Optional[str] = Field(None, description="说明为何要这样构造输入")

    @model_validator(mode="after")
    def validate_script(self) -> "GeneratePoCInputArgs":
        if not self.script.strip():
            raise ValueError("script 不能为空")
        return self

    def to_prompt(self) -> str:
        return f"为触发漏洞，请在文件 {self.file} 下执行以下脚本生成输入：\n{self.script}"

    def short_summary(self) -> str:
        return f"GeneratePoCInput(file={self.file})"

    class Config:
        title = "GeneratePoCInput"


class GeneratePoCInput(Action):
    name: ClassVar[str] = "GeneratePoCInput"
    description: ClassVar[str] = "使用 LLM 编写的脚本构造输入文件，用于触发漏洞"
    args_schema: ClassVar[Type[ActionArguments]] = GeneratePoCInputArgs

    _completion_model: CompletionModel = PrivateAttr()

    def __init__(self, completion_model: CompletionModel):
        super().__init__()
        self._completion_model = completion_model

    def _execute(
        self,
        args: GeneratePoCInputArgs,
        file_context: FileContext,
        workspace: Workspace,
    ) -> Observation:
        
        print(f"🧪 GeneratePoCInputArgs type: {type(GeneratePoCInputArgs)}")

        print(f"[EXECUTE DEBUGDEBUG] GeneratePoCInputArgs schema = {GeneratePoCInputArgs.model_json_schema()}")
        print(f"[EXECUTE DEBUG] 🔧 Running GeneratePoCInput on file: {args.file}")
        print(f"[EXECUTE DEBUG] Script:\n{args.script}\n")
        runner = ScriptRunner(completion_model=self._completion_model)
        try:
            output = runner.run_script(args.file, args.script)
            return Observation(
                message=output[:1000],
                summary="生成输入脚本成功执行",
                extra={
                    "generated_input": output,
                    "script_used": args.script,
                    "source_file": args.file,
                },
                expect_correction=False,
            )
        except Exception as e:
            import traceback
            print("[SCRIPT ERROR] stacktrace:")
            traceback.print_exc()
            return Observation(
                message=f"脚本执行失败: {e}",
                summary="输入生成失败，可能需调整脚本",
                extra={"error": True, "script_used": args.script},
                expect_correction=True,
            )

    @classmethod
    def get_few_shot_examples(cls) -> List[FewShotExample]:
        return [
            FewShotExample.create(
                user_input="我需要生成一个输入文件用于触发 buffer overflow",
                action=GeneratePoCInputArgs(
                    file="vuln.cpp",
                    thoughts="要覆盖 0x20 缓冲区，需要写入超过 32 字节",
                    script="with open('input.txt', 'w') as f:\n    f.write('A' * 64)",
                ),
            ),
            FewShotExample.create(
                user_input="写一个脚本来生成越界输入",
                action=GeneratePoCInputArgs(
                    file="main.cpp",
                    thoughts="构造大字符串以越界读取",
                    script="payload = 'X' * 100\nwith open('input.txt', 'w') as f:\n    f.write(payload)",
                ),
            ),
        ]
