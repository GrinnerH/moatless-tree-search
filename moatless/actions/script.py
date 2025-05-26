# moatless/actions/script.py

import os
import tempfile
import subprocess
from typing import ClassVar, Type, Optional, List

from pydantic import Field, model_validator, PrivateAttr

from moatless.actions.action import Action
from moatless.actions.model import ActionArguments, FewShotExample, Observation
from moatless.file_context import FileContext
from moatless.workspace import Workspace
from moatless.completion.completion import CompletionModel


class ScriptArgs(ActionArguments):
    target_file: str = Field(..., description="与脚本关联的目标源文件路径（如 test.cpp）")
    script: str = Field(..., description="要运行的 Python 脚本内容，可包含格式错误")

    def to_prompt(self) -> str:
        return f"script('{self.target_file}', '''{self.script[:30]}...''')"

    def short_summary(self) -> str:
        return f"script({os.path.basename(self.target_file)})"

    class Config:
        title = "script"

    @model_validator(mode="after")
    def check_script(self) -> "ScriptArgs":
        if not self.script.strip():
            raise ValueError("script 不能为空")
        return self


class Script(Action):
    name: ClassVar[str] = "script"
    description: ClassVar[str] = "运行 Python 脚本，并使用 LLM 修复其格式错误（如缩进）"
    args_schema: ClassVar[Type[ActionArguments]] = ScriptArgs

    completion_model: CompletionModel = Field(..., exclude=True)

    def _execute(
        self,
        args: ScriptArgs,
        file_context: FileContext,
        workspace: Workspace,
    ) -> Observation:
        base_name = os.path.splitext(os.path.basename(args.target_file))[0]
        temp_dir = os.path.join("temp", base_name)
        os.makedirs(temp_dir, exist_ok=True)

        prompt = f"""
Take this python code and fix indentation or any obvious syntax bugs.
Do not change the logic or behavior. 
Return only fixed code, no markdown or explanations.
Code:
{args.script}
""".strip()

        try:
            # 调用模型修复脚本格式
            response = self.completion_model._litellm_base_completion(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "text"},
            )
            fixed_code = response["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return Observation(
                message=f"模型格式修复失败: {str(e)}",
                summary="脚本格式化失败",
                expect_correction=True,
            )

        # 写入修复后的脚本
        fd, path = tempfile.mkstemp(suffix='.py', dir=temp_dir)
        with os.fdopen(fd, 'w') as f:
            f.write(fixed_code)

        try:
            result = subprocess.run(
                ['python3', path],
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )
            return Observation(
                message=result.stdout.strip(),
                summary="脚本运行成功",
                extra={
                    "stderr": result.stderr.strip(),
                    "script": fixed_code,
                }
            )
        except subprocess.CalledProcessError as e:
            return Observation(
                message="运行失败（CalledProcessError）",
                summary="脚本运行失败",
                extra={
                    "returncode": e.returncode,
                    "stdout": e.stdout,
                    "stderr": e.stderr,
                    "script": fixed_code,
                },
                expect_correction=True,
            )
        except Exception as e:
            return Observation(
                message=f"执行异常: {type(e).__name__}: {str(e)}",
                summary="脚本运行异常",
                extra={"script": fixed_code},
                expect_correction=True,
            )

    @classmethod
    def get_few_shot_examples(cls) -> List[FewShotExample]:
        return [
            FewShotExample.create(
                user_input="运行一个脚本：print('hello')",
                action=ScriptArgs(
                    target_file="dummy.cpp",
                    script="print('hello')"
                )
            ),
            FewShotExample.create(
                user_input="执行一个复杂脚本，使用 os.system 编译 cpp",
                action=ScriptArgs(
                    target_file="test.cpp",
                    script="import os\nos.system('g++ test.cpp -o a.out && ./a.out')"
                )
            ),
        ]
